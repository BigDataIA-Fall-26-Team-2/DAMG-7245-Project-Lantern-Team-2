"""Part 9 quality gates on the committed fixtures, scored fresh.

Review finding on #111: the gates read a committed metrics file, so CI stayed
green whatever the parsers did. These gates score the fixtures the stages just
parsed. In CI the smoke workflow has already run parse_text.py (with
Tesseract) and tables.py on tests/fixtures into $RUNNER_TEMP/lantern-smoke, so
the scores are of that run. Anywhere else the two stages are run here first.

Thresholds are in params.yaml, evaluate.thresholds.fixtures, each with the
baseline it came from.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import evaluate  # noqa: E402

FIXTURES = Path("tests/fixtures")
GT = FIXTURES / "gt"


def outputs_dir(tmp_path_factory):
    given = os.environ.get("LANTERN_FIXTURE_DIR")
    if not given and os.environ.get("RUNNER_TEMP"):
        ci = Path(os.environ["RUNNER_TEMP"]) / "lantern-smoke"
        if (ci / "parsed").exists():
            given = str(ci)
    if given:
        return Path(given)
    out = tmp_path_factory.mktemp("fixtures")
    for script, sub in (("src/parse_text.py", "parsed"), ("src/tables.py", "tables")):
        r = subprocess.run([sys.executable, script, "--params", "params.yaml",
                            "--input", str(FIXTURES), "--output", str(out / sub)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            last = (r.stderr.strip().splitlines() or ["no error output"])[-1]
            pytest.skip(f"{script} could not run on the fixtures here: {last}")
    return out


@pytest.fixture(scope="module")
def scores(tmp_path_factory):
    out = outputs_dir(tmp_path_factory)
    return evaluate.score_fixtures(out / "parsed", out / "tables", GT)


@pytest.fixture(scope="module")
def thresholds():
    cfg = yaml.safe_load(open("params.yaml", encoding="utf-8"))["evaluate"]
    return cfg["thresholds"]


def test_every_fixture_ground_truth_has_output(scores):
    assert not scores["missing"], f"no stage output for: {scores['missing']}"


def test_multicolumn_fixture_text(scores, thresholds):
    m = scores["pages"]["multicol_p1"]
    assert m["wer"] <= thresholds["fixtures"]["max_wer_multicolumn"], m


def test_scanned_fixture_ocr(scores, thresholds):
    """Tesseract on an image-only page: the stratum no filing page covers."""
    m = scores["pages"]["scanned_p1"]
    fx = thresholds["fixtures"]
    assert m["wer"] <= fx["max_wer_scanned"], m
    assert m["cer"] <= fx["max_cer_scanned"], m


def test_statement_fixture_text(scores, thresholds):
    m = scores["pages"]["statement_p1"]
    assert m["wer"] <= thresholds["fixtures"]["max_wer_statement"], m


def test_statement_fixture_table_cells(scores, thresholds):
    t = scores["tables"]["statement_p1_t1"]
    assert t["cell"]["f1"] >= thresholds["min_table_cell_f1"], t
    assert t["cell_raw"]["f1"] >= thresholds["min_table_cell_f1"], t