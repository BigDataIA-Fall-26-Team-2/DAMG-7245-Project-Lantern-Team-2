"""Tests for src/xbrl.py helpers (#38). No Arelle and no real filing needed."""
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import xbrl  # noqa: E402


def test_unwrap_strips_sec_envelopes_and_leaves_plain_files_alone():
    assert xbrl.unwrap(b"<XBRL>\n<?xml version='1.0'?><a/>\n</XBRL>\n") == b"<?xml version='1.0'?><a/>\n"
    assert xbrl.unwrap(b"<XML>\n<?xml version='1.0'?><b/>\n</XML>") == b"<?xml version='1.0'?><b/>\n"
    plain = b"<?xml version='1.0'?><c/>\n"
    assert xbrl.unwrap(plain) == plain
    assert xbrl.unwrap(b"<XBRL>\n<?xml version='1.0'?><d/>") == b"<XBRL>\n<?xml version='1.0'?><d/>"  # no closing tag


def test_unwrapped_copy_changes_only_the_copy(tmp_path):
    src = tmp_path / "unpacked"
    src.mkdir()
    (src / "aapl-20250927.xsd").write_bytes(b"<XBRL>\n<?xml version='1.0'?><schema/>\n</XBRL>\n")
    (src / "R1.htm").write_bytes(b"<html>viewer page</html>")

    changed = xbrl.unwrapped_copy(src, tmp_path / "work")

    assert changed == 1
    assert (tmp_path / "work" / "aapl-20250927.xsd").read_bytes().startswith(b"<?xml")
    assert (src / "aapl-20250927.xsd").read_bytes().startswith(b"<XBRL>")  # original untouched


def duration(start, arelle_end):
    return SimpleNamespace(isInstantPeriod=False, isStartEndPeriod=True,
                           startDatetime=datetime.fromisoformat(start),
                           endDatetime=datetime.fromisoformat(arelle_end))


def test_period_fields_subtract_arelle_day_and_label_like_table_columns():
    # Arelle stores date-only ends as midnight of the next day
    assert xbrl.period_fields(duration("2024-09-29", "2025-09-28")) == (
        "duration", "2024-09-29", "2025-09-27", 12, "FY ended 2025-09-27")
    assert xbrl.period_fields(duration("2026-03-29", "2026-06-28")) == (
        "duration", "2026-03-29", "2026-06-27", 3, "3M ended 2026-06-27")
    assert xbrl.period_fields(duration("2025-09-28", "2026-06-28")) == (
        "duration", "2025-09-28", "2026-06-27", 9, "9M ended 2026-06-27")
    instant = SimpleNamespace(isInstantPeriod=True, instantDatetime=datetime.fromisoformat("2025-09-28"))
    assert xbrl.period_fields(instant) == ("instant", None, "2025-09-27", None, "2025-09-27")


def test_precision_orders_exact_then_finer_rounding_then_missing():
    assert xbrl.precision("INF") > xbrl.precision("-6") > xbrl.precision("-8") > xbrl.precision(None)


def test_dedupe_keeps_most_precise_copy_and_counts_conflicts():
    key = {"stem": "AAPL_10K_20250927", "prefix": "us-gaap", "period_type": "instant",
           "start": None, "end": "2024-09-28", "unit": "usd", "dims": ""}
    df = pd.DataFrame([
        {**key, "concept": "UnrecognizedTaxBenefits", "value": 22.0e9, "decimals": "-8"},   # "$22.0 billion" in text
        {**key, "concept": "UnrecognizedTaxBenefits", "value": 22.038e9, "decimals": "-6"},  # 22,038 in the table
        {**key, "concept": "Assets", "value": 364.98e9, "decimals": "-6"},
    ])

    out, conflicts = xbrl.dedupe(df)

    tax = out[out.concept == "UnrecognizedTaxBenefits"]
    assert len(out) == 2 and conflicts == 1
    assert tax["value"].item() == 22.038e9 and tax["n_copies"].item() == 2
    assert list(out.concept) == ["UnrecognizedTaxBenefits", "Assets"]  # original order kept
