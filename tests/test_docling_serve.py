"""Tests for the docling-serve HTTP path in src/docling_parse.py (#83). A fake requests.post stands in for the server."""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("docling_core")
import requests  # noqa: E402
from docling_core.types.doc import DoclingDocument  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def load_module():
    # Load under another name: "docling_parse" is also Docling's own package.
    spec = importlib.util.spec_from_file_location("lantern_docling_parse_serve", ROOT / "src" / "docling_parse.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = load_module()
PARAMS = {"serve_url": "http://serve:5001/", "do_ocr": False, "table_mode": "accurate", "serve_timeout_s": 5}


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_convert_via_serve_posts_file_and_rebuilds_document(tmp_path, monkeypatch):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    seen = {}

    def fake_post(url, files, data, timeout):
        seen.update(url=url, name=files["files"][0], data=data, timeout=timeout)
        return FakeResponse({"status": "success",
                             "document": {"json_content": DoclingDocument(name="a").model_dump(mode="json")}})

    monkeypatch.setattr(requests, "post", fake_post)
    doc = dp.convert_via_serve(pdf, PARAMS)
    assert isinstance(doc, DoclingDocument)
    assert seen["url"] == "http://serve:5001/v1/convert/file"
    assert seen["data"] == {"to_formats": "json", "do_ocr": "false", "table_mode": "accurate"}
    assert seen["name"] == "a.pdf" and seen["timeout"] == 5


def test_convert_via_serve_raises_on_failed_conversion(tmp_path, monkeypatch):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(requests, "post",
                        lambda url, files, data, timeout: FakeResponse({"status": "failure", "errors": ["boom"]}))
    with pytest.raises(RuntimeError, match="docling-serve failed"):
        dp.convert_via_serve(pdf, PARAMS)
