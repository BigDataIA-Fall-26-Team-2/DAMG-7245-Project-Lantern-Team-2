"""Part 7: the config the caller passes is the config that applies.

Review finding on #116: tables.py takes --params, but textract.py read the
root params.yaml on import, so a caller that passed managed.enabled: false
could still trigger an API call. The API is mocked here: no test touches AWS.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from managed import textract  # noqa: E402

ROW = {"accession": "0000320193-26-000020", "company": "Apple Inc.",
       "cik": "0000320193", "ticker": "AAPL", "form": "10-Q",
       "fiscal_year": 2026, "fiscal_period": "Q"}


@pytest.fixture
def no_render(monkeypatch):
    monkeypatch.setattr(textract, "render_page_png", lambda *a, **k: b"page-image")
    monkeypatch.setattr(textract, "page_size_pt", lambda *a, **k: (612.0, 792.0))


def params(tmp_path, enabled):
    return {"managed": {"enabled": enabled, "cache_dir": str(tmp_path / "cache")}}


def test_importing_the_module_reads_no_params_file():
    assert not hasattr(textract, "PARAMS")
    assert not hasattr(textract, "ENABLED")


def test_passed_disabled_config_makes_no_api_call(tmp_path, monkeypatch, no_render):
    def api(*a, **k):
        raise AssertionError("Textract API called although the caller disabled it")
    monkeypatch.setattr(textract, "analyze", api)
    # even if a params.yaml somewhere says enabled: true, the passed one wins
    monkeypatch.setattr(textract, "load_params",
                        lambda *a, **k: {"managed": {"enabled": True}})
    got = textract.fallback_blocks(ROW, Path("x.pdf"), 6,
                                   params=params(tmp_path, False))
    assert got == []


def test_no_params_means_disabled(tmp_path, monkeypatch, no_render):
    def api(*a, **k):
        raise AssertionError("Textract API called with no config passed")
    monkeypatch.setattr(textract, "analyze", api)
    assert textract.fallback_blocks(ROW, Path("x.pdf"), 6) == []


def test_passed_enabled_config_calls_once_and_caches(tmp_path, monkeypatch, no_render):
    calls = []

    def api(image_bytes, region, features):
        calls.append((region, features))
        return {"Blocks": []}
    monkeypatch.setattr(textract, "analyze", api)
    p = params(tmp_path, True)
    p["managed"]["region"] = "us-west-2"
    textract.fallback_blocks(ROW, Path("x.pdf"), 6, params=p)
    textract.fallback_blocks(ROW, Path("x.pdf"), 6, params=p)
    # the passed region is used, and the second call is a cache hit
    assert calls == [("us-west-2", ["TABLES", "LAYOUT"])]
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_enabled_call_path_with_a_mocked_boto3_client(monkeypatch):
    """The live path, without AWS: analyze() builds the client with the passed
    region and sends the passed features."""
    import types
    seen = {}

    class Client:
        def analyze_document(self, **kwargs):
            seen["kwargs"] = kwargs
            return {"Blocks": []}

    fake = types.ModuleType("boto3")

    def client(service, region_name=None):
        seen["service"], seen["region"] = service, region_name
        return Client()
    fake.client = client
    monkeypatch.setitem(sys.modules, "boto3", fake)
    out = textract.analyze(b"img", "us-east-1", ["TABLES", "LAYOUT"])
    assert out == {"Blocks": []}
    assert seen["service"] == "textract" and seen["region"] == "us-east-1"
    assert seen["kwargs"] == {"Document": {"Bytes": b"img"},
                              "FeatureTypes": ["TABLES", "LAYOUT"]}