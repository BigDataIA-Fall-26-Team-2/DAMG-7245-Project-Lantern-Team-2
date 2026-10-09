"""Part 9 quality gates.

Thresholds come from params.yaml, set from the measured baseline with headroom
rather than chosen to pass. Every threshold has a comment saying what the
baseline actually was, so a later tightening or loosening is a visible
decision rather than a silent drift.

The accuracy gates score the export that is on disk now: the metrics fixture
runs src/evaluate.py itself into a temporary file. They never read the
committed reports/metrics.json, so a stale or hand-edited metrics file cannot
make them pass. With no exported filings on disk they are skipped, not passed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# LANTERN_METRICS points the gates at a given metrics file instead of a fresh
# run. Used only to record the failing runs required by Part 9 (the break
# modes): the thresholds must reject a degraded pipeline, not merely accept a
# healthy one.
LANTERN_METRICS = os.environ.get("LANTERN_METRICS")
GT_DIR = Path("data/ground_truth")
EXPORT_DIR = Path("data/export")


def exported_filings():
    return [p for p in EXPORT_DIR.glob("*.jsonl")
            if not p.name.endswith(".docling.jsonl")]


@pytest.fixture(scope="module")
def metrics(tmp_path_factory):
    if LANTERN_METRICS:
        return json.loads(Path(LANTERN_METRICS).read_text(encoding="utf-8"))
    if not exported_filings():
        pytest.skip("no exported filings in data/export; run the pipeline "
                    "(dvc repro export) before the accuracy gates")
    out = tmp_path_factory.mktemp("metrics") / "metrics.json"
    subprocess.run([sys.executable, "src/evaluate.py", "--out", str(out),
                    "--no-plot"], check=True, capture_output=True)
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def thresholds():
    cfg = yaml.safe_load(open("params.yaml", encoding="utf-8"))["evaluate"]
    return cfg["thresholds"]


# --- the ground truth itself ---------------------------------------------

def test_conventions_file_exists():
    assert (GT_DIR / "CONVENTIONS.md").exists(), (
        "the conventions must be written down; a transcription whose rules are "
        "undocumented cannot be reconciled between two transcribers"
    )


def test_ground_truth_pages_present(thresholds):
    n = len(list(GT_DIR.glob("*.gt.txt")))
    assert n >= thresholds["min_gt_pages"]


def test_ground_truth_tables_present(thresholds):
    n = len(list(GT_DIR.glob("*_t*.gt.csv")))
    assert n >= thresholds["min_gt_tables"], (
        "Lab 9 requires at least two statement tables as CSV"
    )


def test_ground_truth_tables_have_required_columns():
    import csv
    for p in GT_DIR.glob("*_t*.gt.csv"):
        with open(p, encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f))
        assert header == ["row_label", "col_label", "raw", "value"], (
            f"{p.name} header is {header}; a spreadsheet round trip is the "
            f"usual cause"
        )


def test_ground_truth_values_are_full_precision():
    """Guards against a spreadsheet round trip.

    Excel reinterprets the value column as scientific notation and saves it
    back rounded to three significant digits, which silently turns
    307003000000 into 307000000000. That produced a table cell F1 of 0.0 with
    no error message, so it is worth a test.
    """
    import csv
    for p in GT_DIR.glob("*_t*.gt.csv"):
        for row in csv.DictReader(open(p, encoding="utf-8-sig", newline="")):
            v = (row["value"] or "").strip()
            assert "E+" not in v.upper(), (
                f"{p.name} has {v!r} in scientific notation; re-run "
                f"write_gt_tables.py and do not open the file in Excel"
            )


# --- accuracy gates ------------------------------------------------------

def test_prose_wer_within_threshold(metrics, thresholds):
    """Prose is where WER measures reading accuracy.

    Baseline: 0.043, 0.047, 0.093, 0.153 on the four prose pages.
    """
    s = metrics["by_stratum"]["traditional"].get("prose")
    assert s, "no prose pages scored"
    assert s["wer_max"] <= thresholds["max_wer_prose"], s


def test_prose_cer_within_threshold(metrics, thresholds):
    s = metrics["by_stratum"]["traditional"].get("prose")
    assert s["cer_mean"] <= thresholds["max_cer_prose"], s


def test_numeric_token_f1_above_threshold(metrics, thresholds):
    """Order-insensitive, so this is the fair reading metric on table pages.

    Baseline: 0.7235 mean across all 16 sampled pages, traditional path
    (repeated numbers counted).
    """
    v = metrics["by_path"]["traditional"]["numeric_f1_mean"]
    assert v >= thresholds["min_numeric_f1"], v


def test_table_cell_f1_above_threshold(metrics, thresholds):
    """Baseline: 1.0 on both hand-keyed statement tables."""
    assert metrics["tables"], "no ground truth tables scored"
    for key, t in metrics["tables"].items():
        assert t["cell"]["f1"] >= thresholds["min_table_cell_f1"], (key, t)


def test_table_value_recall_above_threshold(metrics, thresholds):
    for key, t in metrics["tables"].items():
        assert t["value"]["recall"] >= thresholds["min_table_value_recall"], (
            key, t)


def test_no_sampled_page_missing_from_the_export(metrics):
    """A ground truth page with no output must fail, not vanish.

    Regression test for a review finding: a page the parser lost was skipped
    by the scorer, so two reference pages with output for only one scored a
    perfect WER of 0. Lost pages are now scored as empty and listed here.
    """
    for path_name in ("traditional", "docling"):
        lost = metrics.get("missing", {}).get(path_name, [])
        assert not lost, f"{path_name} lost ground truth pages: {lost}"


def test_only_allowed_pages_are_unmeasured(metrics, thresholds):
    """Pages with ground truth but no export at all must be declared.

    The allowed list lives in params.yaml with the reason, so an unmeasured
    stratum is a visible decision and not a silent gap.
    """
    allowed = set(thresholds.get("allow_unmeasured", []))
    for path_name in ("traditional", "docling"):
        got = set(metrics.get("unmeasured", {}).get(path_name, []))
        assert got <= allowed, (
            f"{path_name} has unmeasured ground truth not declared in "
            f"params.yaml evaluate.thresholds.allow_unmeasured: {got - allowed}")


def test_every_stratum_has_at_least_one_scored_page(metrics):
    """A stratum that silently scores nothing is worse than one that scores
    badly: the report would claim coverage it does not have."""
    scored = metrics["by_stratum"]["traditional"]
    for stratum in ("prose", "statement", "notes", "cover"):
        assert stratum in scored, f"{stratum} has no scored pages"


# --- provenance regression ----------------------------------------------

def test_no_placeholder_table_bbox():
    """Regression test for a real bug found by Part 9.

    Two 10-Q tables carried bbox [0,0,1,1], a one point square at the page
    origin, because the tables stage found a table where the layout stage
    detected no Table region. The record was schema valid and the provenance
    claim was false, which is exactly the gap the schema cannot close.
    """
    if not exported_filings():
        pytest.skip("no exported filings in data/export")
    bad = []
    for p in EXPORT_DIR.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("block_type") != "Table":
                continue
            x0, y0, x1, y1 = r["bbox"]
            if (x1 - x0) < 5 or (y1 - y0) < 5:
                bad.append((p.name, r["block_id"], r["bbox"]))
    assert not bad, f"degenerate table bboxes: {bad}"


def test_table_extractor_matches_tables_log():
    """Regression test for the review finding that every table record named
    camelot even though the log shows 15 of 32 were read by pdfplumber."""
    import csv
    log = Path("data/tables/log/tables_log.csv")
    if not log.exists() or not exported_filings():
        pytest.skip("tables log or exported filings not present")
    expected = {}
    for row in csv.DictReader(open(log, encoding="utf-8-sig", newline="")):
        if str(row.get("accepted", "")).strip().lower() in ("true", "1", "yes"):
            expected[(row["stem"], int(row["page"]))] = row["method"]
    seen = set()
    for p in EXPORT_DIR.glob("*.jsonl"):
        stem = p.stem
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("block_type") != "Table":
                continue
            want = expected.get((stem, r["page"]))
            if want:
                assert r["extractor"] == want, (stem, r["page"],
                                                r["extractor"], want)
                seen.add((stem, r["page"]))
    assert seen, "no table records cross-checked against the log"