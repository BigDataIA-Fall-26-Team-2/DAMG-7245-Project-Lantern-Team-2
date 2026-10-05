"""Detect layout blocks on every rendered page with LayoutParser (EfficientDet, PubLayNet).

Stage: layout. Reads params.yaml:layout, data/rendered/ and its manifest.csv.
Writes data/layout/{stem}.blocks.jsonl and QA overlays in reports/layout/.
"""
import argparse
import csv
import json
import urllib.request
from pathlib import Path

import numpy as np
import pdfplumber
import torch
import yaml
import layoutparser as lp
from PIL import ImageDraw

MODEL_URI = "lp://efficientdet/PubLayNet/tf_efficientdet_d0"
MODEL_PATH = Path("models/publaynet-tf_efficientdet_d0.pth.tar")
# LayoutParser's built-in Dropbox link is dead; the LayoutParser team hosts the same weights on Hugging Face.
MODEL_URL = ("https://huggingface.co/layoutparser/efficientdet/resolve/main/"
             "PubLayNet/tf_efficientdet_d0/publaynet-tf_efficientdet_d0.pth.tar")

# PyTorch >= 2.6 loads checkpoints in "weights only" mode. This checkpoint also stores its
# training args and numpy number types, so allow exactly those (safer than weights_only=False).
_scalar = np._core.multiarray.scalar if hasattr(np, "_core") else np.core.multiarray.scalar
torch.serialization.add_safe_globals([
    (_scalar, "numpy.core.multiarray.scalar"),
    np.dtype, np.dtypes.Float64DType, np.dtypes.Float32DType, np.dtypes.Int64DType,
    argparse.Namespace,
])

DPI = 150         # resolution the page image is rendered at for the detector
K = 72 / DPI      # pixels -> PDF points


def load_model():
    """Load the PubLayNet EfficientDet model, downloading the weights first if missing."""
    if not MODEL_PATH.exists():
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading layout weights -> {MODEL_PATH}")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return lp.AutoLayoutModel(MODEL_URI, model_path=str(MODEL_PATH))


def overlap(a, b):
    """Share of the smaller box covered by the other (0 = apart, 1 = fully inside)."""
    ax1, ay1, ax2, ay2 = a.coordinates
    bx1, by1, bx2, by2 = b.coordinates
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    smaller = min((ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1))
    return ix * iy / smaller if smaller > 0 else 0.0


def detect_page(model, page, params):
    """Detect blocks on one pdfplumber page, dropping low scores and duplicates.

    Returns (page image, kept LayoutParser boxes, records with bbox in points, top-left origin)."""
    img = page.to_image(resolution=DPI).original.convert("RGB")
    raw = sorted((b for b in model.detect(np.array(img)) if b.score >= params["score_threshold"]),
                 key=lambda b: b.score, reverse=True)
    kept = []
    for b in raw:  # highest score first, so a duplicate loses to the stronger box
        if all(overlap(b, k) < params["max_overlap"] for k in kept):
            kept.append(b)
    w, h = float(page.width), float(page.height)
    records = []
    for b in kept:
        x1, y1, x2, y2 = b.coordinates
        bbox = [min(max(x1 * K, 0), w), min(max(y1 * K, 0), h),
                min(max(x2 * K, 0), w), min(max(y2 * K, 0), h)]   # clip to the page
        records.append({"block_type": b.type, "score": round(float(b.score), 3),
                        "bbox": [round(v, 2) for v in bbox]})
    return img, lp.Layout(kept), records


COLORS = {"Text": "blue", "Title": "red", "List": "green", "Table": "orange", "Figure": "purple"}

def draw(img, layout):
    """Draw boxes with type and score (replaces lp.draw_box, which breaks on new Pillow)."""
    out = img.copy()
    d = ImageDraw.Draw(out)
    for b in layout:
        x1, y1, x2, y2 = b.coordinates
        c = COLORS.get(b.type, "black")
        d.rectangle([x1, y1, x2, y2], outline=c, width=3)
        d.text((x1 + 4, y1 + 4), f"{b.type} {b.score:.2f}", fill=c)
    return out


def load_params(path="params.yaml"):
    return yaml.safe_load(Path(path).read_text())

def main(params_path, input_dir, output, qa_dir):
    params = load_params(params_path)["layout"]
    out, qa = Path(output), Path(qa_dir)
    out.mkdir(parents=True, exist_ok=True)
    qa.mkdir(parents=True, exist_ok=True)

    # stem -> doc_id (accession), from Lokesh's render manifest
    manifest = {}
    manifest_path = Path(input_dir) / "manifest.csv"
    if manifest_path.exists():
        with open(manifest_path, newline="") as f:
            manifest = {r["stem"]: r["doc_id"] for r in csv.DictReader(f)}

    model = load_model()
    qa_pages = params.get("qa_pages", {})

    for pdf_path in sorted(Path(input_dir).glob("*.pdf")):
        stem = pdf_path.stem
        doc_id = manifest.get(stem, stem)
        counts, page_rows = {}, []
        with pdfplumber.open(pdf_path) as pdf, open(out / f"{stem}.blocks.jsonl", "w") as f:
            for page in pdf.pages:
                n = page.page_number
                img, kept, recs = detect_page(model, page, params)
                for i, r in enumerate(recs, start=1):
                    rec = {"doc_id": doc_id, "page": n, "block_id": f"p{n:04d}_b{i:03d}",
                           **r, "model": MODEL_URI}
                    f.write(json.dumps(rec) + "\n")
                    counts[r["block_type"]] = counts.get(r["block_type"], 0) + 1
                # one row per page, so blank pages are recorded instead of silently missing
                chars = len((page.extract_text() or "").strip())
                status = "ok" if recs else ("blank" if chars == 0 else "missed")
                page_rows.append({"page": n, "n_blocks": len(recs), "chars": chars, "status": status})
                if n in qa_pages.get(stem, []):
                    draw(img, kept).save(qa / f"{stem}_p{n:04d}.png")

        with open(out / f"{stem}.pages.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["page", "n_blocks", "chars", "status"])
            w.writeheader()
            w.writerows(page_rows)

        blank = [r["page"] for r in page_rows if r["status"] == "blank"]
        missed = [r["page"] for r in page_rows if r["status"] == "missed"]
        print(f"{stem}: {len(page_rows)} pages, blocks {counts}, blank {blank}, MISSED {missed}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--input", default="data/rendered")
    ap.add_argument("--output", default="data/layout")
    ap.add_argument("--qa", default="reports/layout")
    a = ap.parse_args()
    main(a.params, a.input, a.output, a.qa)