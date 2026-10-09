"""metrics.json carries the XBRL match rate (brief Section 5, Appendix C), computed from the
xbrl stage's comparison CSVs; checked here on the committed snapshot in reports/xbrl/."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import evaluate  # noqa: E402


def test_xbrl_match_rates_from_the_snapshot():
    m = evaluate.xbrl_match_rates(ROOT / "reports" / "xbrl")
    assert m["traditional"]["cells"] == m["docling"]["cells"] == 388
    assert m["traditional"]["match_rate"] == 0.8454 and m["docling"]["match_rate"] == 0.8376
    assert m["traditional"]["value_agreement"] == 1.0 and m["docling"]["value_agreement"] == 0.9923
    for path in ("traditional", "docling"):
        assert m[path]["by_statement"]["income"] == m[path]["by_statement"]["balance"] == 1.0


def test_missing_folder_gives_an_empty_section(tmp_path):
    assert evaluate.xbrl_match_rates(tmp_path / "nothing") == {}
