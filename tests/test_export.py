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