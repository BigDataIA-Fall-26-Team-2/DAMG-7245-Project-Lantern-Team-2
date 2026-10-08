"""Unit tests for the #39 PDF-vs-XBRL comparison in src/xbrl.py.

Small hand-made inputs only: no Arelle, no network, no data/ folder, so CI can run them.
Most tests lock in a bug found on the real filings (see docs/ai_log/dhruvi.md, #39).
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import xbrl  # noqa: E402

M = 1_000_000
NS = ('xmlns:link="http://www.xbrl.org/2003/linkbase" '
      'xmlns:xlink="http://www.w3.org/1999/xlink"')
XSD = "https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd"


# ------------------------------------------------------------------ tolerance
def test_tolerance_is_half_a_unit_of_the_last_reported_digit():
    assert xbrl.tolerance(-6) == 500_000
    assert xbrl.tolerance(2) == pytest.approx(0.005)
    for exact in ("INF", None, float("nan")):
        assert xbrl.tolerance(exact) == 0.5


# ------------------------------------------------------------------- classify
def test_classify_match_within_rounding():
    assert xbrl.classify(112_010 * M, 112_010 * M, 500_000) == "match"
    assert xbrl.classify(112_010 * M, 112_010 * M + 400_000, 500_000) == "match"


def test_classify_sign_when_only_the_sign_differs():
    # dividends: printed (11,778) on the cash-flow page, stored positive in XBRL
    assert xbrl.classify(-11_778 * M, 11_778 * M, 500_000) == "sign"


def test_classify_scale_in_both_directions():
    assert xbrl.classify(112_010, 112_010 * M, 500_000) == "scale_x1e6"  # "in millions" not applied
    assert xbrl.classify(112_010 * M * 1000, 112_010 * M, 500_000) == "scale_x1e-3"  # applied twice


def test_classify_mismatch():
    # intangible assets before the fix: wrong concept picked up the total, not the non-current part
    assert xbrl.classify(20_342 * M, 25_417 * M, 500_000) == "mismatch"


def test_classify_missing_values():
    assert xbrl.classify(float("nan"), 5.0, 0.5) == "pdf_missing"
    assert xbrl.classify(5.0, None, 0.5) == "xbrl_missing"


def test_classify_zero_is_never_a_scale_error():
    assert xbrl.classify(0, 300, 0.5) == "mismatch"


# ------------------------------------------------------------------ label map
@pytest.fixture
def entries(tmp_path):
    path = tmp_path / "label_map.yaml"
    path.write_text(
        "lines:\n"
        "  balance:\n"
        "    - {pdf: \"Shareholders' equity: Total shareholders' equity\", concept: StockholdersEquity}\n"
        "    - {pdf: \"Shareholders' equity: Common stock and additional paid-in capital\", "
        "concept: CommonStocksIncludingAdditionalPaidInCapital, match: prefix}\n"
        "    - {pdf: \"Non-current assets: Intangible assets, net\", "
        "concept: IntangibleAssetsNetExcludingGoodwillNoncurrent, prefix: aapl}\n"
    )
    return xbrl.load_label_map(path)["balance"]


def test_manual_map_ignores_curly_quotes_case_and_spacing(entries):
    found = xbrl.manual_candidates(entries, "Shareholders\u2019  equity: TOTAL shareholders\u2019 equity")
    assert found == [("manual", {"prefix": "us-gaap", "concept": "StockholdersEquity", "dims": "",
                              "instant": ""})]


def test_manual_map_prefix_match_survives_filing_specific_share_counts(entries):
    label = ("Shareholders\u2019 equity: Common stock and additional paid-in capital, $0.00001 par value: "
             "50,400,000 shares authorized; 14,773,260 and 15,116,786 shares issued and outstanding")
    assert xbrl.manual_candidates(entries, label)[0][1]["concept"] == "CommonStocksIncludingAdditionalPaidInCapital"


def test_manual_map_is_exact_unless_the_line_says_prefix(entries):
    assert xbrl.manual_candidates(entries, "Shareholders' equity: Total shareholders' equity, beginning") == []


def test_manual_map_carries_extension_prefix(entries):
    found = xbrl.manual_candidates(entries, "Non-current assets: Intangible assets, net")
    assert found[0][1]["prefix"] == "aapl"


# -------------------------------------------------------------------- periods
@pytest.fixture
def bounds():
    facts = pd.DataFrame([{"period_type": "duration", "period_label": "9M ended 2026-06-27",
                           "start": "2025-09-28", "end": "2026-06-27"}])
    return xbrl.period_bounds(facts)


def test_duration_column_also_offers_end_and_opening_instants(bounds):
    assert xbrl.period_options("9M ended 2026-06-27", bounds) == [
        "9M ended 2026-06-27", "2026-06-27", "2025-09-27"]
    assert xbrl.period_options("2026-06-27", bounds) == ["2026-06-27"]


def test_beginning_and_ending_balances_pick_the_right_instant(bounds):
    cash = {"prefix": "us-gaap", "concept": "Cash", "dims": ""}
    idx = {("S", "us-gaap", "Cash", "", "2026-06-27"): (39_544 * M, -6),
           ("S", "us-gaap", "Cash", "", "2025-09-27"): (35_934 * M, -6)}
    begin = xbrl.resolve([("manual", cash)], "S", "9M ended 2026-06-27", 35_934 * M, idx, bounds)
    end = xbrl.resolve([("manual", cash)], "S", "9M ended 2026-06-27", 39_544 * M, idx, bounds)
    assert begin[2] == "2025-09-27" and begin[3] == 35_934 * M
    assert end[2] == "2026-06-27" and end[3] == 39_544 * M


# -------------------------------------------------------------------- resolve
def _other_candidates():
    return [("label", {"prefix": "us-gaap", "concept": "OtherInvesting", "dims": ""}),
            ("label", {"prefix": "us-gaap", "concept": "OtherFinancing", "dims": ""})]


def _other_index():
    p = "9M ended 2026-06-27"
    return {("S", "us-gaap", "OtherInvesting", "", p): (1_780 * M, -6),
            ("S", "us-gaap", "OtherFinancing", "", p): (-184 * M, -6)}


def test_several_concepts_and_no_agreement_is_ambiguous_not_a_guess():
    method, cand, _, value, _ = xbrl.resolve(_other_candidates(), "S", "9M ended 2026-06-27",
                                             -2_037 * M, _other_index(), {})
    assert method == "ambiguous" and cand["concept"] == "" and value is None


def test_value_agreement_picks_the_right_concept_among_several():
    method, cand, _, _, _ = xbrl.resolve(_other_candidates(), "S", "9M ended 2026-06-27",
                                         -1_780 * M, _other_index(), {})
    assert method == "label" and cand["concept"] == "OtherInvesting"  # sign agreement


# ------------------------------------------------------------------ linkbases
@pytest.fixture
def filing(tmp_path):
    """A fake unpacked filing folder: label linkbase plain, presentation linkbase in SEC's envelope."""
    loc = f'<link:loc xlink:type="locator" xlink:href="{XSD}#us-gaap_%s" xlink:label="%s"/>'
    (tmp_path / "aapl-20260627_lab.xml").write_text(
        f'<?xml version="1.0" encoding="utf-8"?><link:linkbase {NS}><link:labelLink xlink:type="extended">'
        + loc % ("RepaymentsOfLongTermDebt", "loc_r")
        + '<link:label xlink:type="resource" xlink:label="lab_r" '
          'xlink:role="http://www.xbrl.org/2003/role/terseLabel">Repayments of term debt</link:label>'
          '<link:labelArc xlink:type="arc" xlink:from="loc_r" xlink:to="lab_r"/>'
          '</link:labelLink></link:linkbase>\n')
    pre = (f'<?xml version="1.0" encoding="utf-8"?><link:linkbase {NS}>'
           '<link:presentationLink xlink:type="extended">'
           + loc % ("CashFlowAbstract", "loc_a") + loc % ("RepaymentsOfLongTermDebt", "loc_r")
           + loc % ("NetIncomeLoss", "loc_n")
           + '<link:presentationArc xlink:type="arc" xlink:from="loc_a" xlink:to="loc_r" '
             'preferredLabel="http://www.xbrl.org/2009/role/negatedLabel"/>'
             '<link:presentationArc xlink:type="arc" xlink:from="loc_a" xlink:to="loc_n"/>'
             '</link:presentationLink></link:linkbase>')
    (tmp_path / "aapl-20260627_pre.xml").write_text("<XBRL>\n" + pre + "\n</XBRL>\n")
    return tmp_path / "aapl-20260627.htm"


def test_label_layer_then_fuzzy_layer(filing):
    labels = xbrl.linkbase_labels(filing)
    assert labels == {"repayments of term debt": [("us-gaap", "RepaymentsOfLongTermDebt")]}
    exact = xbrl.candidates("Financing activities: Repayments of term debt", [], labels, list(labels), 0.85)
    near = xbrl.candidates("Financing activities: Repayment of term debt", [], labels, list(labels), 0.85)
    far = xbrl.candidates("Financing activities: Dividends paid", [], labels, list(labels), 0.85)
    assert exact[0][0] == "label" and near[0][0] == "fuzzy" and far == []
    assert near[0][1]["concept"] == "RepaymentsOfLongTermDebt"


def test_negated_label_read_from_enveloped_presentation_linkbase(filing):
    assert xbrl.negated_concepts(filing) == {("us-gaap", "RepaymentsOfLongTermDebt")}


# ------------------------------------------------------------ pdf_missing (#57)
_BEGIN = {"pdf": "Cash, beginning balances", "concept": "Cash", "instant": "opening"}
_END = {"pdf": "Cash, ending balances", "concept": "Cash", "instant": "end"}
_CASH = {("S", "us-gaap", "Cash", "", "2026-06-27"): (39_544 * M, -6),
         ("S", "us-gaap", "Cash", "", "2025-09-27"): (35_934 * M, -6)}


def test_missing_opening_balance_is_reported_under_its_own_line(bounds):
    # Docling's 10-K cash-flow table dropped the beginning-balances row: only the ending row exists
    seen = {("Cash", "", "2026-06-27", "9M ended 2026-06-27")}
    found = xbrl.missing_cells([_BEGIN, _END], ["9M ended 2026-06-27"], "S", _CASH, bounds, seen)
    assert [(e["pdf"], p) for e, _, p, *_ in found] == [("Cash, beginning balances", "2025-09-27")]


def test_nothing_missing_when_both_balances_were_extracted(bounds):
    seen = {("Cash", "", "2026-06-27", "9M ended 2026-06-27"),
            ("Cash", "", "2025-09-27", "9M ended 2026-06-27")}
    assert xbrl.missing_cells([_BEGIN, _END], ["9M ended 2026-06-27"], "S", _CASH, bounds, seen) == []


def test_opening_balance_that_equals_last_years_ending_is_still_reported():
    # Real case (Docling, 10-K p36): only the ending rows were extracted. FY2025's opening fact
    # (2024-09-28) is also FY2024's ending fact, which WAS extracted; it must not hide the gap.
    facts = pd.DataFrame([
        {"period_type": "duration", "period_label": "FY ended 2025-09-27", "start": "2024-09-29", "end": "2025-09-27"},
        {"period_type": "duration", "period_label": "FY ended 2024-09-28", "start": "2023-10-01", "end": "2024-09-28"}])
    two_years = xbrl.period_bounds(facts)
    idx = {("S", "us-gaap", "Cash", "", d): (v * M, -6)
           for d, v in (("2025-09-27", 3), ("2024-09-28", 2), ("2023-09-30", 1))}
    seen = {("Cash", "", "2025-09-27", "FY ended 2025-09-27"),
            ("Cash", "", "2024-09-28", "FY ended 2024-09-28")}
    found = xbrl.missing_cells([_BEGIN, _END], ["FY ended 2025-09-27", "FY ended 2024-09-28"],
                               "S", idx, two_years, seen)
    assert [(e["pdf"], col, p) for e, col, p, *_ in found] == [
        ("Cash, beginning balances", "FY ended 2025-09-27", "2024-09-28"),
        ("Cash, beginning balances", "FY ended 2024-09-28", "2023-09-30")]


# ------------------------------------------------------------ review fixes (#98)
def test_swapped_beginning_and_ending_balances_fail_instead_of_matching(bounds):
    # Lokesh's case: beginning row holds the ending value (and vice versa)
    begin = {"prefix": "us-gaap", "concept": "Cash", "dims": "", "instant": "opening"}
    end = {"prefix": "us-gaap", "concept": "Cash", "dims": "", "instant": "end"}
    col = "9M ended 2026-06-27"
    _, _, p_b, v_b, d_b = xbrl.resolve([("manual", begin)], "S", col, 39_544 * M, _CASH, bounds)
    _, _, p_e, v_e, d_e = xbrl.resolve([("manual", end)], "S", col, 35_934 * M, _CASH, bounds)
    assert p_b == "2025-09-27" and xbrl.classify(39_544 * M, v_b, xbrl.tolerance(d_b)) == "mismatch"
    assert p_e == "2026-06-27" and xbrl.classify(35_934 * M, v_e, xbrl.tolerance(d_e)) == "mismatch"


def test_balance_instant_comes_from_the_label_when_the_map_has_none():
    assert xbrl.instant_from_label("Cash, cash equivalents, and restricted cash, beginning balances") == "opening"
    assert xbrl.instant_from_label("Financing activities: Cash, cash equivalents, ending balances") == "end"
    assert xbrl.instant_from_label("Net income") == ""


def test_compare_stops_when_a_configured_statement_table_is_missing(tmp_path):
    params = tmp_path / "params.yaml"
    params.write_text("xbrl:\n  fuzzy_cutoff: 0.85\n  statement_pages:\n"
                      "    AAPL_10K_20250927: {income: 32, cash_flow: 36}\n")
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "AAPL_10K_20250927_p0032_t1.csv").write_text("row_label,col_label,raw,value,scale\n")
    with pytest.raises(SystemExit) as err:
        xbrl.compare_main(["--params", str(params), "--tables", str(tables)])
    assert "AAPL_10K_20250927_p0036_t1.csv" in str(err.value)
