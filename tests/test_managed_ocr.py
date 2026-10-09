"""PR #125 review-requested coverage of the Part 7/8 OCR fallback hook."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import parse_text
from managed import textract


@pytest.fixture
def context(tmp_path, monkeypatch):
    config = {"managed": {"enabled": False, "cache_dir": str(tmp_path),
                          "trigger": {"min_ocr_conf": 0.75}}}
    monkeypatch.setattr(textract, "render_page_png", lambda *a: b"fixture")

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled fallback must not call AWS")

    monkeypatch.setattr(textract, "analyze", forbidden)
    monkeypatch.setattr(parse_text, "ocr_page", lambda *a: (
        "Tesseract text", [{"text": "Tesseract", "bbox": [1, 2, 3, 4], "ocr_conf": 60}], 60))
    return config


def page(config):
    return next(parse_text.extract_page_text(
        Path(__file__).parent / "fixtures/scanned.pdf",
        {"min_chars": 20, "junk_ratio": 0.3, "dpi": 300, "language": "eng"}, config))


def cache(config, blocks):
    textract.store(textract.page_hash(b"fixture"), {"Blocks": blocks}, {},
                   config["managed"]["cache_dir"])


def test_disabled_cache_miss_keeps_tesseract(context):
    result = page(context)
    assert result["engine"] == "tesseract"
    assert result["text"] == "Tesseract text"
    assert result["mean_confidence"] == 60
    assert result["managed_status"] == "disabled_cache_miss"


def test_disabled_cache_hit_replaces_text_and_words(context):
    cache(context, [
        {"BlockType": "LINE", "Text": "Managed text"},
        {"BlockType": "WORD", "Text": "Managed", "Confidence": 98,
         "Geometry": {"BoundingBox": {"Left": .1, "Top": .2, "Width": .3, "Height": .1}}},
    ])
    result = page(context)
    with parse_text.pdfplumber.open(Path(__file__).parent / "fixtures/scanned.pdf") as pdf:
        width, height = pdf.pages[0].width, pdf.pages[0].height
    assert result["engine"] == "aws-textract"
    assert result["managed_status"] == "cache_hit"
    assert result["text"] == "Managed text"
    assert result["mean_confidence"] == 98
    assert result["words"][0]["bbox"] == pytest.approx(
        [round(.1 * width, 2), round(.2 * height, 2),
         round(.4 * width, 2), round(.3 * height, 2)])


@pytest.mark.parametrize("confidence,expected", [
    (74.9, "disabled_cache_miss"), (75, "not_needed"),
    (100, "not_needed"), (None, "disabled_cache_miss"),
])
def test_confidence_boundary_and_empty_ocr(context, confidence, expected):
    replacement, status = parse_text.managed_fallback("unused.pdf", 1, 612, 792, confidence, context)
    assert replacement is None
    assert status == expected


def test_empty_response_keeps_tesseract(context):
    cache(context, [])
    result = page(context)
    assert result["engine"] == "tesseract"
    assert result["text"] == "Tesseract text"
    assert result["managed_status"] == "empty_response"
