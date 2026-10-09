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
    fake.load_manifest = lambda *a, **k: {"x": {}}
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


def test_the_stage_params_reach_the_fallback(tmp_path, monkeypatch):
    """Review finding on #116: the params the stage was run with must be the
    ones that decide the managed switch, not the root params.yaml."""
    seen = {}
    fake_textract(monkeypatch, [])

    def capture(*a, **k):
        seen.update(k)
        return []
    sys.modules["managed.textract"].fallback_blocks = capture
    log = {"method": "camelot-stream", "score": 0.1, "numeric_rows": 10}
    tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS)
    assert seen.get("params") is PARAMS


def test_a_stale_managed_answer_is_removed(tmp_path):
    stale = tmp_path / "managed" / "x_p0001.blocks.jsonl"
    stale.parent.mkdir()
    stale.write_text("{}\n", encoding="utf-8")
    log = {"method": "camelot-stream", "score": 0.9, "numeric_rows": 10}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS) == ""
    assert not stale.exists()


def test_a_failed_check_keeps_the_real_error(tmp_path, monkeypatch):
    """Review finding on #116: a broad catch turned every failure into a bare
    "error". The exception text is now kept for tables_log.csv."""
    def boom(*a, **k):
        raise ModuleNotFoundError("No module named 'boto3'")
    fake_textract(monkeypatch, [])
    sys.modules["managed.textract"].fallback_blocks = boom
    log = {"method": "camelot-stream", "score": 0.1, "numeric_rows": 10}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, PARAMS) == "error"
    assert "boto3" in log["fallback_error"]


def test_disabled_config_through_the_real_module_makes_no_api_call(tmp_path, monkeypatch):
    """The real configuration boundary: tables.managed_fallback -> the real
    managed.textract module. The root params says enabled: true, the params the
    stage was run with say enabled: false. No API call may happen."""
    from managed import textract
    monkeypatch.setattr(textract, "render_page_png", lambda *a, **k: b"page")
    monkeypatch.setattr(textract, "load_params",
                        lambda *a, **k: {"managed": {"enabled": True}})
    monkeypatch.setattr(textract, "load_manifest",
                        lambda *a, **k: {"x": {"accession": "0000320193-26-000020"}})

    def api(*a, **k):
        raise AssertionError("Textract API called although enabled is false")
    monkeypatch.setattr(textract, "analyze", api)
    params = {"managed": {"enabled": False, "cache_dir": str(tmp_path / "cache"),
                          "trigger": {"min_table_score": 0.5}},
              "tables": {"min_numeric_rows": 3}}
    log = {"method": "camelot-stream", "score": 0.1, "numeric_rows": 10}
    assert tables.managed_fallback(Path("x.pdf"), 1, log, tmp_path, params) == "miss"
    assert "fallback_error" not in log