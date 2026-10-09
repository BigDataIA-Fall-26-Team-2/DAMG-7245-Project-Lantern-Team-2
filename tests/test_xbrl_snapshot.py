"""P11: the committed snapshot in reports/xbrl/ reproduces the published XBRL results without DVC."""
from pathlib import Path

import pandas as pd

SNAP = Path(__file__).resolve().parents[1] / "reports" / "xbrl"


def load(path):
    return pd.read_csv(SNAP / f"comparison_{path}.csv")


def test_snapshot_gives_the_published_match_rates():
    trad, doc = load("traditional"), load("docling")
    assert len(trad) == len(doc) == 388
    assert trad.status.value_counts().to_dict() == {"match": 328, "sign": 60}
    assert doc.status.value_counts().to_dict() == {"match": 325, "sign": 60, "pdf_missing": 3}


def test_income_and_balance_match_fully_on_both_paths():
    for path in ("traditional", "docling"):
        c = load(path)
        for statement in ("income", "balance"):
            assert (c[c.statement == statement].status == "match").all(), (path, statement)


def test_every_sign_cell_is_explained_by_the_presentation_linkbase():
    for path in ("traditional", "docling"):
        sign = load(path)
        sign = sign[sign.status == "sign"]
        assert sign.cause.fillna("").str.contains("negated label").all(), path


def test_facts_snapshot_has_every_fact():
    facts = pd.read_csv(SNAP / "facts.csv")
    assert len(facts) == 1553
    assert {"concept", "value", "unit", "decimals", "period_type", "dims"} <= set(facts.columns)
