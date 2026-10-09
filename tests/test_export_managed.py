"""Part 7: a fallback table must reach the final export, replacing the
low-score Part 2 table on its page and never duplicating it.

Review finding on #116: the tables stage wrote Textract tables to
data/tables/managed/ and logged "used", but the export never read that folder,
so a successful fallback did not change the exported data.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import export  # noqa: E402
from schema import Block  # noqa: E402

STEM = "AAPL_10Q_20260627"
BASE = {
    "schema": "lantern/1.0", "doc_id": "0000320193-26-000020",
    "company": "Apple Inc.", "cik": "0000320193", "ticker": "AAPL",
    "form": "10-Q", "fiscal_year": 2026, "fiscal_period": "Q",
    "section": None, "units": "pt", "origin": "top-left", "text": None,
    "bbox": [40.0, 100.0, 570.0, 400.0],
}
TABLE = {"columns": ["", "col1"], "rows": [["Net sales", "94,036"]],
         "raw_cells": [["Net sales", "94,036"]], "scale": None}


def managed_rec(page, n=1):
    return dict(BASE, page=page, block_id=f"p{page:04d}_b{500 + n:03d}",
                block_type="Table", table=TABLE, extractor="aws-textract",
                extractor_version="boto3 1.43.106", ocr=True, ocr_conf=0.99)


def part2_block(page):
    return Block.model_validate(dict(
        BASE, page=page, block_id=f"p{page:04d}_b901", block_type="Table",
        table=TABLE, extractor="camelot-stream", extractor_version="camelot",
        ocr=False, ocr_conf=None))


def write_managed(tmp_path, page):
    text = dict(BASE, page=page, block_id=f"p{page:04d}_b502",
                block_type="Text", text="Segment", table=None,
                extractor="aws-textract", extractor_version="boto3",
                ocr=True, ocr_conf=0.9)
    p = tmp_path / f"{STEM}_p{page:04d}.blocks.jsonl"
    p.write_text(json.dumps(managed_rec(page)) + "\n" + json.dumps(text) + "\n",
                 encoding="utf-8")


def test_only_table_blocks_are_read(tmp_path):
    write_managed(tmp_path, 16)
    got = export.managed_table_blocks(STEM, managed_dir=tmp_path)
    assert list(got) == [16]
    assert [b.block_id for b in got[16]] == ["p0016_b501"]


def test_managed_table_replaces_the_low_score_part2_table(tmp_path):
    """Forced low-score page with a cache hit: the export changes, and the
    page ends up with exactly one table, the managed one."""
    write_managed(tmp_path, 16)
    part2 = [part2_block(16), part2_block(20)]
    merged, rows = export.merge_managed_tables(
        STEM, part2, export.managed_table_blocks(STEM, managed_dir=tmp_path))
    on_16 = [b for b in merged if b.page == 16]
    assert [b.extractor for b in on_16] == ["aws-textract"]
    assert [b.page for b in merged if b.extractor != "aws-textract"] == [20]
    assert rows == [{"stem": STEM, "page": 16, "replaced": "p0016_b901",
                     "managed": "p0016_b501", "extractor": "aws-textract"}]


def test_managed_table_fills_a_page_with_no_part2_table(tmp_path):
    write_managed(tmp_path, 16)
    merged, rows = export.merge_managed_tables(
        STEM, [], export.managed_table_blocks(STEM, managed_dir=tmp_path))
    assert [b.block_id for b in merged] == ["p0016_b501"]
    assert rows[0]["replaced"] == ""


def test_no_managed_answers_leaves_part2_tables_alone(tmp_path):
    part2 = [part2_block(16)]
    merged, rows = export.merge_managed_tables(
        STEM, part2, export.managed_table_blocks(STEM, managed_dir=tmp_path / "x"))
    assert merged == part2 and rows == []