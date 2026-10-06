"""Unit tests for src/tables.py helpers (CI-safe: no PDFs or data needed)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import tables  # noqa: E402


@pytest.mark.parametrize("raw, scale, expected", [
    ("307,003", 1e6, 307_003_000_000.0),     # plain number, "in millions"
    ("(5,571)", 1e6, -5_571_000_000.0),      # parentheses = negative
    ("(14,264", 1e6, -14_264_000_000.0),     # closing parenthesis dropped by pdfplumber (bake-off)
    ("$ 7.46", 1.0, 7.46),                   # per-share row: currency dropped, no scaling
    ("1,234(1)", 1.0, 1234.0),               # trailing footnote marker
    ("\u2014", 1e6, 0.0),                    # em dash = zero
    ("Net income", 1.0, None),               # text is not a number
    ("27,", 1.0, None),                      # day from "June 27," is not a number
])
def test_normalize(raw, scale, expected):
    result = tables.normalize(raw, scale)
    assert result == (pytest.approx(expected) if expected is not None else None)


def test_is_number_cell():
    assert tables.is_number_cell("14,656,110")
    assert tables.is_number_cell("(5,571)")
    assert not tables.is_number_cell("June 27,")
    assert not tables.is_number_cell("27,")


@pytest.mark.parametrize("header, n_cols, expected", [
    (["Years ended", "September 27, September 28, September 30,", "2025 2024 2023"], 3,
     ["FY ended 2025-09-27", "FY ended 2024-09-28", "FY ended 2023-09-30"]),
    (["Three Months Ended Nine Months Ended", "June 27, June 28, June 27, June 28,", "2026 2025 2026 2025"], 4,
     ["3M ended 2026-06-27", "3M ended 2025-06-28", "9M ended 2026-06-27", "9M ended 2025-06-28"]),
    (["September 27, September 28,", "2025 2024"], 2, ["2025-09-27", "2024-09-28"]),
    ([], 2, ["col1", "col2"]),
])
def test_column_labels(header, n_cols, expected):
    assert tables.column_labels(header, n_cols) == expected


def test_page_lines():
    lines = tables.page_lines("Products $ 307,003 $ 294,866\nNon-current assets:\n"
                              "Retained earnings/(Accumulated deficit) 11,326 (14,264)")
    assert lines == [("Products", (307003.0, 294866.0)),
                     ("Non-current assets:", ()),
                     ("Retained earnings/(Accumulated deficit)", (11326.0, -14264.0))]


def test_gray_level_white_is_invisible():
    assert tables.gray_level((1.0, 1.0, 1.0)) >= 0.9
    assert tables.gray_level((0.9333, 0.9333, 0.9333)) >= 0.9
    assert tables.gray_level((0.0, 0.0, 0.0)) < 0.9
    assert tables.gray_level(None) < 0.9


PAGE_TEXT = """Apple Inc.
CONSOLIDATED BALANCE SHEETS
(In millions, except number of shares, which are reflected in thousands, and par value)
September 27, September 28,
2025 2024
Current assets:
Marketable securities $ 18,763 $ 35,228
Total current assets 147,957 152,987
Non-current assets:
Marketable securities 77,723 91,479
Total non-current assets 211,284 211,993
Total assets $ 359,241 $ 364,980
Apple Inc. | 2025 Form 10-K | 31"""


def test_to_long_labels_from_page_text_when_extractor_truncates_a_header():
    # pdfplumber-style grid: the "Non-" fragment of "Non-current assets:" is lost.
    df = pd.DataFrame([
        ["", "September 27,", "September 28,"],
        ["", "2025", "2024"],
        ["Current assets:", "", ""],
        ["Marketable securities", "$ 18,763", "$ 35,228"],
        ["Total current assets", "147,957", "152,987"],
        ["current assets:", "", ""],
        ["Marketable securities", "77,723", "91,479"],
        ["Total non-current assets", "211,284", "211,993"],
        ["Total assets", "$ 359,241", "$ 364,980"],
        ["Apple Inc. | 2025 Form 10-K |", "31", ""],
    ])
    rows, skipped = tables.to_long(df, PAGE_TEXT)
    out = pd.DataFrame(rows, columns=tables.COLUMNS)
    labels = list(dict.fromkeys(out.row_label))
    assert labels == ["Current assets: Marketable securities", "Current assets: Total current assets",
                      "Non-current assets: Marketable securities", "Non-current assets: Total non-current assets",
                      "Total assets"]
    assert list(dict.fromkeys(out.col_label)) == ["2025-09-27", "2024-09-28"]
    assert out.groupby("row_label").size().max() == 2          # no duplicate labels
    assert skipped == 1                                          # the page footer
    nc = out[(out.row_label == "Non-current assets: Marketable securities") & (out.col_label == "2025-09-27")]
    assert nc.value.iloc[0] == pytest.approx(77_723_000_000.0) and nc.scale.iloc[0] == 1e6


# --- Reruns must not leave stale or partial table CSVs (same issue as PR #92 review) ---
STEM = "AAPL_10K_20250927"


def _touch(folder, name):
    (folder / name).write_text("row_label,col_label,raw,value,scale\nOLD,x,1,1,1\n")


def test_clear_page_csvs_one_page_keeps_other_pages_and_filings(tmp_path):
    for name in [f"{STEM}_p0032_t1.csv", f"{STEM}_p0034_t1.csv", "AAPL_10Q_20260627_p0032_t1.csv"]:
        _touch(tmp_path, name)

    tables.clear_page_csvs(tmp_path, STEM, 32)

    assert sorted(p.name for p in tmp_path.glob("*.csv")) == [
        f"{STEM}_p0034_t1.csv", "AAPL_10Q_20260627_p0032_t1.csv"]


def test_clear_page_csvs_whole_filing_keeps_other_filing_and_log(tmp_path):
    for name in [f"{STEM}_p0001_t1.csv", f"{STEM}_p0032_t1.csv", "AAPL_10Q_20260627_p0004_t1.csv"]:
        _touch(tmp_path, name)
    (tmp_path / "log").mkdir()
    _touch(tmp_path / "log", "tables_log.csv")

    tables.clear_page_csvs(tmp_path, STEM)

    assert sorted(p.name for p in tmp_path.glob("*.csv")) == ["AAPL_10Q_20260627_p0004_t1.csv"]
    assert (tmp_path / "log" / "tables_log.csv").exists()


def test_write_table_csv_removes_partial_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / f"{STEM}_p0032_t1.csv"

    def half_write(self, target, *args, **kwargs):
        Path(target).write_text("row_label,col_label\nNet sa")  # simulate a write cut off mid-file
        raise OSError("simulated write failure")

    monkeypatch.setattr(pd.DataFrame, "to_csv", half_write)

    with pytest.raises(OSError):
        tables.write_table_csv([], path)
    assert not path.exists()
