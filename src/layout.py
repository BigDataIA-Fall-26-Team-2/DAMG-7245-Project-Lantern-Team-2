"""Detect layout blocks on every rendered page with LayoutParser (EfficientDet, PubLayNet).

Stage: layout. Reads params.yaml:layout, data/rendered/ and its manifest.csv.
Writes data/layout/{stem}.blocks.jsonl, data/layout/{stem}.pages.csv,
figure crops in data/figures/, and QA overlays in reports/layout/.
"""
import argparse
import csv
import json
import re
import urllib.request
from pathlib import Path

import numpy as np
import pdfplumber
import pytesseract
import yaml
from PIL import ImageDraw, ImageOps
import tables as tbl   # Dhruvi's P2 extractor; extract_best_df is a shared function in CONTRACTS.md

MODEL_URI = "lp://efficientdet/PubLayNet/tf_efficientdet_d0"
MODEL_PATH = Path("models/publaynet-tf_efficientdet_d0.pth.tar")
# LayoutParser's built-in Dropbox link is dead; the LayoutParser team hosts the same weights on Hugging Face.
MODEL_URL = ("https://huggingface.co/layoutparser/efficientdet/resolve/main/"
             "PubLayNet/tf_efficientdet_d0/publaynet-tf_efficientdet_d0.pth.tar")

DPI = 150         # resolution the page image is rendered at for the detector
K = 72 / DPI      # pixels -> PDF points
TEXT_TYPES = {"Text", "Title", "List", "Table"}   # boxes whose text we read (Table: placeholder until P2 routing)
# Apple's running page footer, e.g. "Apple Inc. | 2025 Form 10-K | 5" or "... Form 10-Q | 12"
FOOTER = re.compile(r"form\s+10-[kq]\s*\|\s*\d+\s*$", re.IGNORECASE)


def is_footer(text):
    """True if a block's text is the running page footer, not a real heading."""
    return bool(text) and bool(FOOTER.search(text.strip().splitlines()[-1]))

def load_model():
    """Load the PubLayNet EfficientDet model, downloading the weights first if missing."""
    import torch
    import layoutparser as lp

    # PyTorch >= 2.6 loads checkpoints in "weights only" mode. This checkpoint also stores its
    # training args and numpy number types, so allow exactly those (safer than weights_only=False).
    _scalar = np._core.multiarray.scalar if hasattr(np, "_core") else np.core.multiarray.scalar
    torch.serialization.add_safe_globals([
        (_scalar, "numpy.core.multiarray.scalar"),
        np.dtype, np.dtypes.Float64DType, np.dtypes.Float32DType, np.dtypes.Int64DType,
        argparse.Namespace,
    ])

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
    import layoutparser as lp

    # Render the full mediabox: pdfplumber's coordinates use the mediabox, but by default it renders only
    # the cropbox, which shifted every box on the cropped, rotated multicolumn fixture.
    img = page.to_image(resolution=DPI, force_mediabox=True).original.convert("RGB")
    expected = (round(float(page.width) * DPI / 72), round(float(page.height) * DPI / 72))
    if abs(img.size[0] - expected[0]) > 2 or abs(img.size[1] - expected[1]) > 2:
        raise ValueError(f"page {page.page_number}: rendered {img.size}, expected {expected}; "
                         "pixel->point conversion would be wrong")
     # PubLayNet is black-on-white; flip dark designed pages (e.g. annual-report spreads) before detecting
    inverted = np.asarray(img.convert("L")).mean() / 255 < params["dark_page_brightness"]
    if inverted:
        img = ImageOps.invert(img)
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
                        "bbox": [round(v, 2) for v in bbox], "inverted": bool(inverted)})
    return img, lp.Layout(kept), records


def reading_order(records, gap):
    """Sort blocks for reading: find columns by clustering block left edges, then read
    columns left to right and each column top to bottom.

    Left edges are sorted; a new column starts wherever the next edge jumps by more than `gap`
    points. A single-column page stays one column, so it simply reads top to bottom."""
    if not records:
        return records
    xs = sorted(r["bbox"][0] for r in records)
    starts = [xs[0]] + [b for a, b in zip(xs, xs[1:]) if b - a > gap]   # left edge of each column
    def column(r):
        return max(i for i, s in enumerate(starts) if r["bbox"][0] >= s)
    return sorted(records, key=lambda r: (column(r), r["bbox"][1], r["bbox"][0]))


def block_text(page, bbox, ocr_dpi, pad=0.0):
    """Text inside a box via pdfplumber; OCR the crop with Tesseract only if pdfplumber finds nothing.

    pad widens the box left and right only (the detector's boxes often clip first/last letters);
    no vertical padding, so we don't pull in lines from neighbouring blocks."""
    x0, top, x1, bottom = bbox
    x0, x1 = max(x0 - pad, 0), min(x1 + pad, float(page.width))
    crop = page.crop((x0, top, x1, bottom))
    text = (crop.extract_text() or "").strip()
    if text:
        return text, False
    img = crop.to_image(resolution=ocr_dpi).original
    return pytesseract.image_to_string(img).strip(), True

def route_table(pdf_path, page, bbox, pad, params_path):
    """Send a Table block to the P2 extractor.

    The box is stretched to the full page width, because the audit found the detector's Table boxes
    often cover only the number columns (not the row labels), and padded vertically by `pad`."""
    _, top, _, bottom = bbox
    wide = [0.0, max(top - pad, 0.0), float(page.width), min(bottom + pad, float(page.height))]
    try:
        df, info = tbl.extract_best_df(str(pdf_path), page.page_number, wide, params_path)
    except Exception as e:  # one bad table shouldn't stop the whole stage
        return None, {"accepted": False, "error": f"{type(e).__name__}: {e}",
                      "routed_bbox": [round(v, 2) for v in wide]}
    info = {**info, "routed_bbox": [round(v, 2) for v in wide]}
    return (df.to_dict(orient="records") if df is not None else None), info


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


def main(params_path, input_dir, output, qa_dir, figures_dir):
    all_params = load_params(params_path)
    params = all_params["layout"]
    ocr_dpi = all_params["ocr"]["dpi"]          # reuse Lokesh's OCR resolution (Part 1)
    out, qa, figs = Path(output), Path(qa_dir), Path(figures_dir)
    for d in (out, qa, figs):
        d.mkdir(parents=True, exist_ok=True)

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
        section = ""   # most recent Title; carries across pages until the next one
        with pdfplumber.open(pdf_path) as pdf, open(out / f"{stem}.blocks.jsonl", "w") as f:
            for page in pdf.pages:
                n = page.page_number
                img, kept, recs = detect_page(model, page, params)
                recs = reading_order(recs, params["column_gap_pt"])
                for i, r in enumerate(recs, start=1):     # ids follow reading order
                    block_id = f"p{n:04d}_b{i:03d}"
                    text, used_ocr = None, False
                    if r["block_type"] in TEXT_TYPES:
                        text, used_ocr = block_text(page, r["bbox"], ocr_dpi, params["text_pad_pt"])
                    table, table_info = None, None
                    if r["block_type"] == "Table":
                        table, table_info = route_table(pdf_path, page, r["bbox"], params["pad_pt"], params_path)
                    if table is not None:
                        extractor, version = table_info["method"], table_info["extractor_version"]
                    elif text is not None:
                        extractor, version = ("tesseract" if used_ocr else "pdfplumber"), None
                    else:
                        extractor, version = None, None

                    footer = is_footer(text)
                    if r["block_type"] == "Title" and text and not footer:
                        section = text.splitlines()[0][:200]
                    if r["block_type"] == "Figure":
                        page.crop(r["bbox"]).to_image(resolution=DPI).save(figs / f"{stem}_{block_id}.png")
                    rec = {"doc_id": doc_id, "page": n, "block_id": block_id, **r, "model": MODEL_URI,
                           "section": section, "text": text, "ocr": used_ocr, "footer": footer,
                           "table": table, "table_info": table_info,
                           "extractor": extractor, "extractor_version": version}
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
    ap.add_argument("--figures", default="data/figures")
    a = ap.parse_args()
    main(a.params, a.input, a.output, a.qa, a.figures)