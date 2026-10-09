"""Smoke test for app/app.py (#59): it runs headlessly and the net income preset works.

Needs the real pipeline outputs in data/, so it skips itself where they are absent (CI).
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_READY = (ROOT / "data/rendered/manifest.csv").exists() and \
             (ROOT / "data/xbrl/comparison_traditional.csv").exists()

pytestmark = pytest.mark.skipif(not DATA_READY, reason="needs data/rendered and data/xbrl outputs")


def test_app_runs_and_net_income_preset_lands_on_the_income_statement():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=180).run()
    assert not at.exception

    at.sidebar.button[0].click().run()
    assert not at.exception
    assert at.session_state["page"] == 32
    assert at.session_state["cell"].startswith("Net income  |  FY ended 2025-09-27")
