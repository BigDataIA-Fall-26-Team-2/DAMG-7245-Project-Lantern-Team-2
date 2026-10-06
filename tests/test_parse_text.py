"""P1 regression checks for routing, coordinate conversion, and safe output."""
import csv
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import parse_text

ROOT = Path(__file__).resolve().parents[1]
PARAMS = yaml.safe_load((ROOT / "params.yaml").read_text())["ocr"]


def test_ocr_signals_are_independent():
    assert parse_text.ocr_reason("", PARAMS)[0] == "low_char_count"
    assert parse_text.ocr_reason("(cid:123) " * 30, PARAMS)[0] == "high_junk_ratio"
    assert parse_text.ocr_reason("Readable financial statement with enough characters", PARAMS)[0] == ""


def test_tesseract_boxes_use_actual_raster_dimensions():
    image = MagicMock(width=2550, height=3300)
    data = {"text": ["", "Net", "income", "112010"], "conf": [-1, 90, 80, 70],
            "left": [0, 100, 200, 300], "top": [0, 150, 150, 250],
            "width": [0, 50, 80, 90], "height": [0, 40, 40, 40],
            "block_num": [0, 1, 1, 1], "par_num": [0, 1, 1, 1], "line_num": [0, 1, 1, 2]}
    with patch.object(parse_text, "convert_from_path", return_value=[image]), \
         patch.object(parse_text.pytesseract, "image_to_data", return_value=data):
        text, words, confidence = parse_text.ocr_page("unused.pdf", 2, 612, 792, PARAMS)
    assert words[0]["bbox"] == pytest.approx([24, 36, 36, 45.6])
    assert text == "Net income\n112010"
    assert confidence == 80
    image.close.assert_called_once()


def test_native_statement_does_not_invoke_ocr():
    with patch.object(parse_text, "ocr_page", side_effect=AssertionError("unexpected OCR")):
        page = list(parse_text.extract_page_text(ROOT / "tests/fixtures/statement.pdf", PARAMS))[0]
    assert not page["ocr"]
    assert "112,010" in page["text"]
    assert page["words"]
    for word in page["words"]:
        x0, top, x1, bottom = word["bbox"]
        assert 0 <= x0 <= x1 <= 612
        assert 0 <= top <= bottom <= 792


def test_failed_run_preserves_existing_output(tmp_path):
    output = tmp_path / "parsed"
    output.mkdir()
    (output / "ocr_log.csv").write_text("previous run")
    with patch.object(parse_text, "extract_page_text", side_effect=RuntimeError("OCR failed")):
        with pytest.raises(RuntimeError, match="OCR failed"):
            parse_text.main(ROOT / "params.yaml", ROOT / "tests/fixtures", output)
    assert (output / "ocr_log.csv").read_text() == "previous run"
    assert not list(output.glob(".parse-*"))


def test_output_has_manifest_identity_and_replaces_old_pages(tmp_path):
    source, output = tmp_path / "source", tmp_path / "parsed"
    source.mkdir(); output.mkdir()
    (source / "statement.pdf").write_bytes((ROOT / "tests/fixtures/statement.pdf").read_bytes())
    (source / "manifest.csv").write_text("stem,doc_id\nstatement,0000320193-25-000079\n")
    (output / "statement_p0002.txt").write_text("stale page")
    parse_text.main(ROOT / "params.yaml", source, output)
    assert not (output / "statement_p0002.txt").exists()
    record = json.loads((output / "statement.words.jsonl").read_text().splitlines()[0])
    assert record["doc_id"] == "0000320193-25-000079"
    assert record["page"] == 1
    with (output / "ocr_log.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1 and rows[0]["engine"] == "pdfplumber"


def test_rotated_native_boxes_use_displayed_dimensions():
    with parse_text.pdfplumber.open(ROOT / "tests/fixtures/multicolumn.pdf") as pdf:
        width, height = pdf.pages[0].width, pdf.pages[0].height
    page = list(parse_text.extract_page_text(ROOT / "tests/fixtures/multicolumn.pdf", PARAMS))[0]
    assert width > height
    for word in page["words"]:
        x0, top, x1, bottom = word["bbox"]
        assert 0 <= x0 <= x1 <= width
        assert 0 <= top <= bottom <= height
