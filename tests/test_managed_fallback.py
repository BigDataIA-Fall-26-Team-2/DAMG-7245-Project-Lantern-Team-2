"""Part 7: the managed fallback hook inside the Part 2 tables stage.

The hook must only fire when a table was found but scored low, and must never
call the API or fail the stage when managed.enabled is false.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tables  # noqa: E402

PARAMS = {"managed": {"trigger": {"min_table_score": 0.5}},
          "tables": {"min_numeric_rows": 3}}


def fake_textract(monkeypatch, blocks):
    fake = types.ModuleType("managed.textract")
    fake.load_manifest = lambda: {"x": {}}
    fake.fallback_blocks = lambda *a, **k: blocks
    pkg = types.ModuleType("managed")
    pkg.textract = fake
    monkeypatch.setitem(sys.modules, "managed", pkg)
    monkeypatch.setitem(sys.modules, "managed.textract", fake)


def test_no_table_found_means_no_check(tmp_path):
    log = {"method": "", "score": 0.0}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS) == ""


def test_empty_candidate_means_no_check(tmp_path, monkeypatch):
    """Regression: 45 of 91 prose pages had a camelot-stream candidate with
    score 0.0 and no numeric rows. A page with no real table must not fire."""
    fake_textract(monkeypatch, [])
    log = {"method": "camelot-stream", "score": 0.0, "numeric_rows": 0}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS) == ""


def test_good_score_means_no_check(tmp_path):
    log = {"method": "camelot-stream", "score": 0.9, "numeric_rows": 10}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS) == ""


def test_low_score_with_nothing_cached_is_a_miss(tmp_path, monkeypatch):
    fake_textract(monkeypatch, [])
    log = {"method": "camelot-stream", "score": 0.1, "numeric_rows": 10}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS) == "miss"
    assert not (tmp_path / "managed").exists()


def test_a_broken_check_never_fails_the_stage(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("pdftoppm")
    fake_textract(monkeypatch, [])
    sys.modules["managed.textract"].fallback_blocks = boom
    log = {"method": "camelot-stream", "score": 0.1, "numeric_rows": 10}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS) == "error"