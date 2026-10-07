"""Regression test for extract_best_df(..., bbox=...) (Part 3 routing, PR #100).

The scale note ("in millions") and the period headers sit ABOVE a statement table. A layout
bbox around the table must still produce the same scale, periods and values as no bbox.
Uses the committed fixture tests/fixtures/statement.pdf (10-K FY2025 income statement), so it
runs in CI without data/.
"""
import sys
from pathlib import Path

import pdfplumber
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import tables  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "statement.pdf"
PARAMS = ROOT / "params.yaml"

pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="statement fixture not present")


def box_below_header(pdf, label="Net sales"):
    with pdfplumber.open(pdf) as p:
        pg = p.pages[0]
        hit = pg.search(label, regex=False)[0]
        return [0, hit["top"] - 2, pg.width, pg.height]


def test_bbox_below_the_header_keeps_scale_periods_and_values():
    full, _ = tables.extract_best_df(FIXTURE, 1, params_path=PARAMS)
    boxed, _ = tables.extract_best_df(FIXTURE, 1, bbox=box_below_header(FIXTURE), params_path=PARAMS)
    assert boxed is not None
    assert not boxed.col_label.astype(str).str.match(r"col\d").any(), "period headers lost"
    assert set(boxed.col_label) == set(full.col_label)
    assert set(boxed.scale) == set(full.scale)
    key = ["row_label", "col_label"]
    merged = full.merge(boxed, on=key, suffixes=("_full", "_box"))
    assert len(merged) == len(full) == len(boxed)
    assert (merged.value_full.fillna(0) == merged.value_box.fillna(0)).all()


def test_net_income_is_in_full_units_with_a_bbox():
    boxed, _ = tables.extract_best_df(FIXTURE, 1, bbox=box_below_header(FIXTURE), params_path=PARAMS)
    ni = boxed[(boxed.row_label == "Net income") & (boxed.col_label == "FY ended 2025-09-27")]
    assert ni.value.iloc[0] == 112_010_000_000
