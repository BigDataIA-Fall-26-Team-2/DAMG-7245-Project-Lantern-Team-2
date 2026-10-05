"""Regression tests for the Part 2 bake-off (#17): reruns must never score stale CSVs.

PR #92 review: a rerun that returned fewer tables, no tables, or an error left old
_tK.csv files in the results folder, and score_cells.py scored them as new output.
These tests use fake extraction methods and a temp folder: no PDFs or Camelot needed.
"""
import importlib.util
from pathlib import Path

import pandas as pd

BAKEOFF_DIR = Path(__file__).resolve().parents[1] / "prototyping" / "dhruvi" / "bakeoff"
STEM, PAGE = "AAPL_10K_20250927", 32


def load(name):
    """Import a bake-off script by file path (the prototyping folder is not a package)."""
    spec = importlib.util.spec_from_file_location(name, BAKEOFF_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bakeoff = load("bakeoff")
score_cells = load("score_cells")


def table(label, value):
    """One extracted table in the (df, accuracy, whitespace) shape bakeoff methods return."""
    return (pd.DataFrame([[label, value]]), None, None)


def csvs(folder, method, page=PAGE):
    return sorted(p.name for p in Path(folder).glob(f"{STEM}_p{page:04d}_{method}_t*.csv"))


class UnwritableTable:
    """Stands in for a DataFrame whose CSV write fails part-way through a run."""
    size = 1

    def to_csv(self, *args, **kwargs):
        raise OSError("simulated write failure")


def test_rerun_with_fewer_tables_removes_stale_csvs(tmp_path):
    three = [table("Total net sales", "416,161"), table("Net income", "112,010"), table("Total", "1")]
    bakeoff.run_method(tmp_path, STEM, PAGE, "camelot-stream", lambda: three)
    assert len(csvs(tmp_path, "camelot-stream")) == 3

    rec = bakeoff.run_method(tmp_path, STEM, PAGE, "camelot-stream",
                             lambda: [table("Net income", "112,010")])

    assert rec["status"] == "ok" and rec["n_tables"] == 1
    assert csvs(tmp_path, "camelot-stream") == [f"{STEM}_p0032_camelot-stream_t1.csv"]
    assert score_cells.method_rows(tmp_path, STEM, PAGE, "camelot-stream") == [("netincome", ["112,010"])]


def test_rerun_with_no_tables_leaves_nothing_to_score(tmp_path):
    bakeoff.run_method(tmp_path, STEM, PAGE, "camelot-stream", lambda: [table("Total net sales", "416,161")])

    rec = bakeoff.run_method(tmp_path, STEM, PAGE, "camelot-stream", lambda: [])

    assert rec["status"] == "no_tables"
    assert csvs(tmp_path, "camelot-stream") == []
    assert score_cells.method_rows(tmp_path, STEM, PAGE, "camelot-stream") == []


def test_failed_run_leaves_no_partial_output(tmp_path):
    bakeoff.run_method(tmp_path, STEM, PAGE, "camelot-stream", lambda: [table("Total net sales", "416,161")])

    # _t1 is written, then writing _t2 fails: neither the old file nor the partial _t1 may survive
    rec = bakeoff.run_method(tmp_path, STEM, PAGE, "camelot-stream",
                             lambda: [table("Net income", "112,010"), (UnwritableTable(), None, None)])

    assert rec["status"] == "error" and "OSError" in rec["error"]
    assert csvs(tmp_path, "camelot-stream") == []
    assert score_cells.method_rows(tmp_path, STEM, PAGE, "camelot-stream") == []


def test_clearing_is_scoped_to_one_page_and_method(tmp_path):
    bakeoff.run_method(tmp_path, STEM, PAGE, "pdfplumber-text", lambda: [table("Net income", "112,010")])
    bakeoff.run_method(tmp_path, STEM, 34, "camelot-stream", lambda: [table("Total assets", "1")])

    bakeoff.run_method(tmp_path, STEM, PAGE, "camelot-stream", lambda: [])

    assert csvs(tmp_path, "pdfplumber-text") == [f"{STEM}_p0032_pdfplumber-text_t1.csv"]
    assert csvs(tmp_path, "camelot-stream", page=34) == [f"{STEM}_p0034_camelot-stream_t1.csv"]
