import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from schema import SCHEMA_VERSION, validate_record, validate_jsonl

EXPORT_DIR = Path("data/export")


def good_record():
    return {
        "schema": SCHEMA_VERSION,
        "doc_id": "0000320193-25-000079",
        "company": "Apple Inc.",
        "cik": "0000320193",
        "ticker": "AAPL",
        "form": "10-K",
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "page": 1,
        "section": "Item 1",
        "block_id": "p0001_b001",
        "block_type": "Text",
        "bbox": [72.0, 100.0, 540.0, 130.0],
        "units": "pt",
        "origin": "top-left",
        "text": "The Company designs, manufactures and markets smartphones.",
        "table": None,
        "extractor": "pdfplumber",
        "extractor_version": "0.11.4",
        "ocr": False,
        "ocr_conf": None,
        "source_path": "data/rendered/AAPL_10K_20250927.pdf",
        "sha256": "a" * 64,
    }


def test_good_record_validates():
    assert validate_record(good_record()).block_id == "p0001_b001"


@pytest.mark.parametrize(
    "field,value",
    [
        ("doc_id", "bad"),
        ("cik", "320193"),
        ("block_id", "page1_block1"),
        ("page", 0),
        ("schema", "lantern/0.9"),
        ("units", "px"),
        ("origin", "bottom-left"),
        ("block_type", "Paragraph"),
        ("sha256", "not-a-hash"),
        ("sha256", "A" * 64),
        ("source_path", ""),
        ("source_path", "data\\rendered\\AAPL_10K_20250927.pdf"),
    ],
)
def test_malformed_field_is_rejected(field, value):
    rec = good_record()
    rec[field] = value
    with pytest.raises(ValidationError):
        validate_record(rec)


def test_bbox_must_be_top_left_oriented():
    rec = good_record()
    rec["bbox"] = [72.0, 130.0, 540.0, 100.0]
    with pytest.raises(ValidationError):
        validate_record(rec)


def test_table_block_without_table_is_rejected():
    rec = good_record()
    rec["block_type"] = "Table"
    rec["table"] = None
    with pytest.raises(ValidationError):
        validate_record(rec)


def test_block_with_no_payload_is_rejected():
    rec = good_record()
    rec["text"] = None
    rec["table"] = None
    with pytest.raises(ValidationError):
        validate_record(rec)


def test_ocr_without_confidence_is_rejected():
    rec = good_record()
    rec["ocr"] = True
    rec["ocr_conf"] = None
    with pytest.raises(ValidationError):
        validate_record(rec)


def test_unknown_field_is_rejected():
    rec = good_record()
    rec["inverted"] = False
    with pytest.raises(ValidationError):
        validate_record(rec)


def test_table_rows_must_be_rectangular():
    rec = good_record()
    rec["block_type"] = "Table"
    rec["text"] = None
    rec["table"] = {
        "columns": ["", "col1", "col2"],
        "rows": [["Revenue", "100"]],
        "raw_cells": [["Revenue", "100", "200"]],
        "scale": "1000.0",
    }
    with pytest.raises(ValidationError):
        validate_record(rec)


@pytest.mark.skipif(
    not (EXPORT_DIR / "AAPL_10K_20250927.jsonl").exists(),
    reason="export output not present; run dvc repro or src/export.py first",
)
def test_exported_jsonl_is_valid():
    ok, errors = validate_jsonl(EXPORT_DIR / "AAPL_10K_20250927.jsonl")
    assert errors == []
    assert ok > 0

@pytest.mark.parametrize("field", ["source_path", "sha256"])
def test_provenance_fields_are_required(field):
    """Appendix B lists source_path and sha256 as minimum fields."""
    rec = good_record()
    del rec[field]
    with pytest.raises(ValidationError):
        validate_record(rec)


# --- Part 5: dei facts, file hash, section fallback ------------------------

import adapters  # noqa: E402
import export  # noqa: E402

IXBRL = (
    '<html><body><div style="display:none">'
    '<ix:nonNumeric contextRef="c-1" name="dei:DocumentFiscalYearFocus" id="f-1">2026</ix:nonNumeric>'
    '<ix:nonNumeric id="f-2" name="dei:DocumentFiscalPeriodFocus" contextRef="c-1"> Q3 </ix:nonNumeric>'
    '</div></body></html>'
)


def test_fiscal_fields_come_from_dei_facts(tmp_path):
    p = tmp_path / "aapl-20260627.htm"
    p.write_text(IXBRL, encoding="utf-8")
    assert adapters.dei_fiscal(str(p)) == (2026, "Q3")


def test_missing_ixbrl_falls_back(tmp_path):
    assert adapters.dei_fiscal(str(tmp_path / "absent.htm")) == (None, None)


def test_file_sha256_is_the_real_hash(tmp_path):
    import hashlib
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.7 test")
    assert adapters.file_sha256(p) == hashlib.sha256(b"%PDF-1.7 test").hexdigest()


def test_section_falls_back_to_nearest_title_before_any_item():
    t = export.SectionTracker()
    assert t.update({"block_type": "Title", "text": "Table of Contents"}) == "Table of Contents"
    assert t.update({"block_type": "Text", "text": "Apple Inc."}) == "Table of Contents"
    assert t.update({"block_type": "Title", "text": "Item 1. Business"}) == "Item 1"
    # once an Item is seen it wins over later Titles
    assert t.update({"block_type": "Title", "text": "Products"}) == "Item 1"


def test_tables_get_the_section_of_the_block_before_them():
    text = validate_record(dict(good_record(), section="Item 8",
                                bbox=[72.0, 100.0, 540.0, 130.0]))
    table = validate_record(dict(
        good_record(), section=None, block_id="p0001_b901", block_type="Table",
        text=None, bbox=[72.0, 200.0, 540.0, 400.0],
        table={"columns": ["", "col1"], "rows": [["Net sales", "1"]],
               "raw_cells": [["Net sales", "1"]], "scale": None}))
    out = export.fill_sections([table, text])
    assert [b.section for b in out] == ["Item 8", "Item 8"]


@pytest.mark.skipif(
    not (EXPORT_DIR / "AAPL_10Q_20260627.jsonl").exists(),
    reason="export output not present; run dvc repro or src/export.py first",
)
def test_exported_10q_carries_the_dei_quarter_and_a_real_hash():
    rec = json.loads(open(EXPORT_DIR / "AAPL_10Q_20260627.jsonl",
                          encoding="utf-8").readline())
    assert rec["fiscal_period"].startswith("Q") and rec["fiscal_period"] != "Q"
    assert rec["source_path"].endswith("AAPL_10Q_20260627.pdf")
    assert len(rec["sha256"]) == 64