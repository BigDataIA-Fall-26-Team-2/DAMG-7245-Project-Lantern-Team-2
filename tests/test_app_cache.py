"""Lokesh's review on #120: cached readers must see a file rewritten by a pipeline rerun."""
import importlib.util
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_app():
    spec = importlib.util.spec_from_file_location("lantern_app", ROOT / "app" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # __name__ is not __main__, so the app itself does not start
    return module


def bump(path):
    later = time.time_ns() + 2_000_000_000
    os.utime(path, ns=(later, later))


def test_read_csv_sees_a_rewritten_file(tmp_path):
    app = load_app()
    f = tmp_path / "comparison.csv"
    f.write_text("value\n1\n")
    assert app.read_csv(f).value.tolist() == [1]
    f.write_text("value\n2\n")
    bump(f)
    assert app.read_csv(f).value.tolist() == [2]


def test_read_jsonl_sees_a_rewritten_file(tmp_path):
    app = load_app()
    f = tmp_path / "records.jsonl"
    f.write_text('{"page": 1}\n')
    assert app.read_jsonl(f) == [{"page": 1}]
    f.write_text('{"page": 2}\n')
    bump(f)
    assert app.read_jsonl(f) == [{"page": 2}]
