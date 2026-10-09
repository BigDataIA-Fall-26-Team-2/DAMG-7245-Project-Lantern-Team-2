"""metrics.json carries the XBRL match rate (brief Section 5, Appendix C), computed from the
xbrl stage's comparison CSVs; both paths are required and missing or empty inputs fail clearly."""
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "reports" / "xbrl"
sys.path.insert(0, str(ROOT / "src"))
import evaluate  # noqa: E402


def test_xbrl_match_rates_from_the_snapshot():
    m = evaluate.xbrl_match_rates(SNAP)
    assert m["traditional"]["cells"] == m["docling"]["cells"] == 388
    assert m["traditional"]["match_rate"] == 0.8454 and m["docling"]["match_rate"] == 0.8376
    assert m["traditional"]["value_agreement"] == 1.0 and m["docling"]["value_agreement"] == 0.9923
    for path in ("traditional", "docling"):
        assert m[path]["by_statement"]["income"] == m[path]["by_statement"]["balance"] == 1.0


def test_missing_folder_fails_clearly(tmp_path):
    with pytest.raises(FileNotFoundError, match="run the xbrl stage"):
        evaluate.xbrl_match_rates(tmp_path / "nothing")


def test_one_missing_path_fails_and_names_the_file(tmp_path):
    shutil.copy(SNAP / "comparison_traditional.csv", tmp_path)
    with pytest.raises(FileNotFoundError, match="comparison_docling.csv"):
        evaluate.xbrl_match_rates(tmp_path)


def test_header_only_comparison_fails(tmp_path):
    shutil.copy(SNAP / "comparison_traditional.csv", tmp_path)
    header = (SNAP / "comparison_docling.csv").read_text().splitlines()[0]
    (tmp_path / "comparison_docling.csv").write_text(header + "\n")
    with pytest.raises(ValueError, match="no comparison rows"):
        evaluate.xbrl_match_rates(tmp_path)
