"""Regression tests for the table bbox fallback in src/export.py.

Raised in review on ba994ba: when the layout stage detects no Table region on
a page, the earlier fix used the union of the remaining detected blocks. On a
page whose only detection is a heading, that exported the table pointing at
the heading: a narrow, confident-looking box in the wrong place. These tests
pin the three cases apart.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from export import table_bbox_for  # noqa: E402

SIZES = {1: (612.0, 792.0), 2: (595.0, 842.0)}


def test_paired_one_to_one_uses_the_detection():
    boxes = [[100.0, 200.0, 500.0, 400.0]]
    bbox, precision, note = table_bbox_for(1, 1, boxes, 1, SIZES)
    assert precision == "detected"
    assert bbox == [100.0, 200.0, 500.0, 400.0]
    assert note == ""


def test_two_detections_two_csvs_pair_in_order():
    boxes = [[10.0, 20.0, 300.0, 100.0], [10.0, 400.0, 300.0, 500.0]]
    assert table_bbox_for(1, 1, boxes, 2, SIZES)[0] == boxes[0]
    assert table_bbox_for(1, 2, boxes, 2, SIZES)[0] == boxes[1]


def test_count_disagreement_unions_only_table_regions():
    """Union is honest here: every box in it is a real Table detection."""
    boxes = [[10.0, 20.0, 300.0, 100.0], [20.0, 400.0, 320.0, 500.0]]
    bbox, precision, note = table_bbox_for(1, 1, boxes, 1, SIZES)
    assert precision == "union"
    assert bbox == [10.0, 20.0, 320.0, 500.0]
    assert "2 layout Table regions" in note


def test_no_table_region_uses_the_full_page_not_other_blocks():
    """The case from review.

    With no Table detection the bbox must be the page, regardless of what
    else was detected. A heading at [50, 20, 550, 45] must not become the
    table's location.
    """
    bbox, precision, note = table_bbox_for(1, 1, [], 1, SIZES)
    assert precision == "page"
    assert bbox == [0.0, 0.0, 612.0, 792.0]
    assert "full page" in note


def test_no_table_region_uses_that_page_s_own_dimensions():
    bbox, _, _ = table_bbox_for(2, 1, [], 1, SIZES)
    assert bbox == [0.0, 0.0, 595.0, 842.0]


def test_unknown_page_size_falls_back_to_letter_and_says_so():
    bbox, precision, note = table_bbox_for(99, 1, [], 1, SIZES)
    assert precision == "page"
    assert bbox == [0.0, 0.0, 612.0, 792.0]
    assert "assumed US Letter" in note


def test_fallback_bbox_is_never_degenerate():
    """Guards the original [0, 0, 1, 1] placeholder from coming back."""
    for page in (1, 2, 99):
        bbox, _, _ = table_bbox_for(page, 1, [], 1, SIZES)
        assert bbox[2] - bbox[0] > 100
        assert bbox[3] - bbox[1] > 100


@pytest.mark.parametrize("precision,boxes,page_tables", [
    ("detected", [[1.0, 2.0, 3.0, 4.0]], 1),
    ("union", [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]], 1),
    ("page", [], 1),
])
def test_precision_label_is_always_set(precision, boxes, page_tables):
    """Every table record's bbox provenance is classified, so the export log
    can report how many boxes are approximate."""
    assert table_bbox_for(1, 1, boxes, page_tables, SIZES)[1] == precision