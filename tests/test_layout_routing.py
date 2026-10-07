"""Integration regression test for P3 table routing (review on #100).

On 10-K p32 the detector's Table box covers only the number columns, below the period headers and
the "(In millions...)" note. route_table stretches it to full width and calls extract_best_df; the
result must keep the FY periods and full-unit values. Uses the committed statement fixture, no model.
"""
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import layout  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "statement.pdf"
PARAMS = ROOT / "params.yaml"


def test_routed_numbers_only_box_keeps_periods_and_scale():
    with pdfplumber.open(FIXTURE) as pdf:
        page = pdf.pages[0]
        top = page.search("Net sales", regex=False)[0]["top"] - 2      # first table row, below the headers
        numbers_only = [362.0, top, 605.0, 557.0]                      # like the detector's box on 10-K p32
        table, info = layout.route_table(FIXTURE, page, numbers_only, 2.0, PARAMS)
    assert info["accepted"]
    assert not any(str(r["col_label"]).startswith("col") for r in table), "period headers lost"
    ni = [r for r in table if r["row_label"] == "Net income" and r["col_label"] == "FY ended 2025-09-27"]
    assert ni and ni[0]["value"] == 112_010_000_000
