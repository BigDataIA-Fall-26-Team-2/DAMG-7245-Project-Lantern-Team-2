"""P3 tuning: how much horizontal padding stops the detector's boxes clipping first letters."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
import pdfplumber
from layout import block_text

PADS = [0, 2, 4, 6, 8, 12]
STEMS = ["AAPL_10K_20250927", "AAPL_10Q_20260627"]

rows = []
for stem in STEMS:
    blocks = [json.loads(l) for l in open(f"data/layout/{stem}.blocks.jsonl")]
    # only text-like blocks that pdfplumber could read (skip OCR'd ones, they don't clip the same way)
    blocks = [b for b in blocks if b["block_type"] in {"Text", "Title", "List"} and not b["ocr"]]
    with pdfplumber.open(f"data/rendered/{stem}.pdf") as pdf:
        for pad in PADS:
            lower = chars = 0
            for b in blocks:
                text, _ = block_text(pdf.pages[b["page"] - 1], b["bbox"], 300, pad)
                lower += bool(text) and text[0].islower()
                chars += len(text)
            rows.append({"stem": stem, "pad_pt": pad, "blocks": len(blocks),
                         "lowercase_start": lower, "total_chars": chars})
            print(rows[-1])

out = Path("prototyping/shravya/text_pad_sweep.csv")
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("saved", out)