"""Tests for absorbing row labels into extracted tables in src/layout.py (Part 9 eval.md finding 6)."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))   # layout.py imports tables.py from src/


def load_layout():
    spec = importlib.util.spec_from_file_location("lantern_layout_absorb", ROOT / "src" / "layout.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:   # model packages missing in the lightweight CI env
        pytest.skip(f"layout dependencies not installed: {e}")
    return mod


def word(text, x0, x1, top, bottom):
    return {"text": text, "x0": x0, "x1": x1, "top": top, "bottom": bottom}


class FakePage:
    def __init__(self, words):
        self._words = words

    def extract_words(self):
        return self._words


WORDS = [word("Net", 6, 20, 120, 130), word("sales", 22, 45, 120, 130),        # row label, left of the table box
         word("Unrelated", 6, 60, 160, 170), word("note", 62, 80, 160, 170),   # paragraph inside the table's rows
         word("307,003", 400, 440, 120, 130)]                                   # figure, inside the table box
RECS = [{"block_type": "Table", "bbox": [362.0, 100.0, 603.0, 200.0], "score": 0.9},
        {"block_type": "Text", "bbox": [6.0, 118.0, 46.0, 132.0], "score": 0.9},
        {"block_type": "Text", "bbox": [6.0, 158.0, 81.0, 172.0], "score": 0.9}]
PARAMS = {"pad_pt": 2.0, "text_pad_pt": 8}
TABLE = [{"row_label": "Net sales", "col_label": "FY ended 2025-09-27", "raw": "307,003"}]


def run(monkeypatch, p2_tokens):
    layout = load_layout()
    monkeypatch.setattr(layout, "route_table", lambda *a, **k: (TABLE, {"accepted": True}))
    recs = [dict(r) for r in RECS]
    return layout.absorb_table_rows("x.pdf", FakePage(WORDS), recs, PARAMS, "params.yaml", p2_tokens)


def test_label_in_both_tables_is_absorbed_and_box_widened(monkeypatch):
    recs, routed = run(monkeypatch, p2_tokens={"net", "sales", "307", "003"})
    types = [r["block_type"] for r in recs]
    assert types == ["Table", "Text"]                      # label absorbed, unrelated paragraph kept
    table = recs[0]
    assert table["bbox"][0] == 6                           # widened to the label's left edge
    assert table["detected_bbox"] == [362.0, 100.0, 603.0, 200.0]
    assert routed[0][1]["absorbed_blocks"] == 1


def test_label_missing_from_part2_tables_is_kept(monkeypatch):
    recs, _ = run(monkeypatch, p2_tokens={"307", "003"})   # export's tables lack the label: keep it
    assert [r["block_type"] for r in recs] == ["Table", "Text", "Text"]
