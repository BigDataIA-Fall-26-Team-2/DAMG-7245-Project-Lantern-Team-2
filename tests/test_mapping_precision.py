"""#82: scoring of the no-dictionary mapping against the verified comparison."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mapping_precision import scores  # noqa: E402

BASE = {"stem": "X", "statement": "income", "page": 1, "period_label": "FY"}


def frame(rows):
    return pd.DataFrame([dict(BASE, **r) for r in rows])


def test_right_wrong_and_unmapped_cells_are_scored():
    ref = frame([{"pdf_label": "Gross margin", "prefix": "us-gaap", "concept": "GrossProfit", "dims": None},
                 {"pdf_label": "Net sales: Products", "prefix": "us-gaap", "concept": "Revenues", "dims": "ProductMember"},
                 {"pdf_label": "Earnings per share: Basic", "prefix": "us-gaap", "concept": "EarningsPerShareBasic", "dims": None}])
    auto = frame([{"pdf_label": "Gross margin", "prefix": "us-gaap", "concept": "GrossProfit", "dims": ""},
                  {"pdf_label": "Net sales: Products", "prefix": "srt", "concept": "ProductMember", "dims": None},
                  {"pdf_label": "Earnings per share: Basic", "prefix": None, "concept": None, "dims": None}])
    s = scores(ref, auto)
    assert (s["cells"], s["mapped"], s["right"]) == (3, 2, 1)
    assert s["precision"] == 0.5 and s["wrong_labels"] == "Products" and s["unmapped_labels"] == "Basic"


def test_empty_and_missing_dims_count_as_the_same():
    ref = frame([{"pdf_label": "Gross margin", "prefix": "us-gaap", "concept": "GrossProfit", "dims": None}])
    auto = frame([{"pdf_label": "Gross margin", "prefix": "us-gaap", "concept": "GrossProfit", "dims": ""}])
    assert scores(ref, auto)["precision"] == 1.0
