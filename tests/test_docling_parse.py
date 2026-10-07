"""Regression tests for src/docling_parse.py (review on #101: stale outputs after a rerun)."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "statement.pdf"   # 10-K p32, committed to git


def load_module():
    # Load under another name: "docling_parse" is also Docling's own package, so a plain import would clash.
    spec = importlib.util.spec_from_file_location("lantern_docling_parse", ROOT / "src" / "docling_parse.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = load_module()

HEADER = ["", "Years ended - September 27, 2025", "Years ended - September 28, 2024",
          "Years ended - September 30, 2023"]
NET_INCOME = ["Net income", "$ 112,010", "$ 93,736", "$ 96,995"]          # matches a line on the fixture page
NOT_ON_PAGE = ["Nothing", "987,654", "876,543", "765,432"]                # matches no line, so it won't normalize


def fake_table(rows, page=1):
    """A stand-in for a Docling TableItem: just the attributes export_tables uses."""
    df = pd.DataFrame(rows, columns=HEADER)
    return SimpleNamespace(prov=[SimpleNamespace(page_no=page)], export_to_dataframe=lambda doc=None: df)


def regenerate(tables, out):
    """What main() does for one filing: clear its old outputs, then export the current tables."""
    dp.clear_outputs("statement", out)
    return dp.export_tables(SimpleNamespace(tables=tables), "statement", FIXTURE, out)


def test_clear_outputs_only_touches_this_filing(tmp_path):
    (tmp_path / "tables").mkdir()
    mine = [tmp_path / "S.md", tmp_path / "S_p0002.md", tmp_path / "S_p0001_t2_raw.csv",
            tmp_path / "tables" / "S_p0001_t2.csv"]
    other = tmp_path / "tables" / "OTHER_p0001_t1.csv"
    for f in mine + [other]:
        f.write_text("x")
    assert dp.clear_outputs("S", tmp_path) == len(mine)
    assert not any(f.exists() for f in mine)
    assert other.exists()


def test_rerun_with_fewer_tables_drops_stale_csvs(tmp_path):
    regenerate([fake_table([NET_INCOME]), fake_table([NET_INCOME])], tmp_path)
    assert (tmp_path / "tables" / "statement_p0001_t2.csv").exists()

    written, empty = regenerate([fake_table([NET_INCOME])], tmp_path)
    assert (written, empty) == (1, 0)
    assert not (tmp_path / "tables" / "statement_p0001_t2.csv").exists()
    assert not (tmp_path / "statement_p0001_t2_raw.csv").exists()


def test_table_that_no_longer_normalizes_leaves_no_csv(tmp_path):
    regenerate([fake_table([NET_INCOME])], tmp_path)
    assert (tmp_path / "tables" / "statement_p0001_t1.csv").exists()

    written, empty = regenerate([fake_table([NOT_ON_PAGE])], tmp_path)
    assert (written, empty) == (0, 1)
    assert not (tmp_path / "tables" / "statement_p0001_t1.csv").exists()


SCANNED = ROOT / "tests" / "fixtures" / "scanned.pdf"   # image-only; page 2 is 10-K p32 as a picture
CAPTION = "(In millions, except number of shares, which are reflected in thousands, and per-share amounts)"


def test_ocr_table_on_image_only_page_is_kept(tmp_path):
    """No PDF text layer: to_long must use what Docling read (caption + rows) instead of dropping the table."""
    table = fake_table([NET_INCOME], page=2)
    caption = SimpleNamespace(prov=[SimpleNamespace(page_no=2)], text=CAPTION)
    doc = SimpleNamespace(tables=[table], iterate_items=lambda: iter([(caption, 0), (table, 0)]))

    written, empty = dp.export_tables(doc, "scanned", SCANNED, tmp_path)
    assert (written, empty) == (1, 0)

    rows = pd.read_csv(tmp_path / "tables" / "scanned_p0002_t1.csv")
    net = rows[rows["row_label"] == "Net income"]
    assert len(net) == 3
    assert net["value"].iloc[0] == 112010000000.0      # scaled: the caption came from Docling's text
