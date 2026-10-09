"""Part 7 stretch: Google Document AI (Form Parser) on the same pages as Textract.

Outside the DVC pipeline on purpose: it changes no stage, no data/managed and
no dvc.lock. The same 150 DPI page images that went to Textract are sent, and
the answers are scored with evaluate.py's own functions against the same
ground truth, so the comparison is on identical inputs.

Cache: reports/gcp/<sha256 of the page image>.json. Without --call it reads the
cache only and makes no API call.

Needs, only for --call:
    GCP_PROJECT, GCP_PROCESSOR_ID, GCP_LOCATION (default "us")
    GOOGLE_APPLICATION_CREDENTIALS pointing at a key file outside the repo

    python scripts/gcp_compare.py --call     first run, 3 paid pages
    python scripts/gcp_compare.py            every run after, from cache

Tested with google-cloud-documentai 3.16.0. Not in requirements.txt, because
nothing in the pipeline imports it.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import evaluate as ev  # noqa: E402
from managed import textract as tx  # noqa: E402

CACHE = ROOT / "reports" / "gcp"

# the same three pages Part 7 sent to Textract
PAGES = [
    ("AAPL_10K_20250927", ROOT / "data/rendered/AAPL_10K_20250927.pdf", 32),
    ("AAPL_10Q_20260627", ROOT / "data/rendered/AAPL_10Q_20260627.pdf", 6),
    ("scanned", ROOT / "tests/fixtures/scanned.pdf", 1),
]


def g(d, camel, snake=None, default=None):
    """Document JSON can come camelCase or snake_case."""
    if d is None:
        return default
    if camel in d:
        return d[camel]
    if snake and snake in d:
        return d[snake]
    return default


def anchor_text(doc_text, layout):
    anchor = g(layout, "textAnchor", "text_anchor", {}) or {}
    out = []
    for seg in g(anchor, "textSegments", "text_segments", []) or []:
        start = int(g(seg, "startIndex", "start_index", 0) or 0)
        end = int(g(seg, "endIndex", "end_index", 0) or 0)
        out.append(doc_text[start:end])
    return " ".join("".join(out).split())


def bbox_pt(layout, w_pt, h_pt):
    poly = g(layout, "boundingPoly", "bounding_poly", {}) or {}
    verts = g(poly, "normalizedVertices", "normalized_vertices", []) or []
    if not verts:
        return None
    xs = [float(v.get("x", 0) or 0) * w_pt for v in verts]
    ys = [float(v.get("y", 0) or 0) * h_pt for v in verts]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]


def inside(box, area):
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return area[0] <= cx <= area[2] and area[1] <= cy <= area[3]


def row_cells(doc_text, row):
    texts = [anchor_text(doc_text, g(c, "layout", default={})) for c in g(row, "cells", default=[])]
    if not texts:
        return None
    # A lone "$" is a currency column, not a value: same rule as Part 2.
    # Google can return a cell with no letter or digit in it (seen on 10-K p32,
    # "Other income/(expense), net"); it is joined to the cell before it, so it
    # does not count as a column and shift the rest of the row.
    values = []
    for t in texts[1:]:
        if not t or t == "$":
            continue
        if not any(ch.isalnum() for ch in t) and t not in ("-", "\u2014", "\u2013") and values:
            values[-1] = values[-1] + t
            continue
        values.append(t)
    return [texts[0]] + values


def records_from_document(doc, w_pt, h_pt):
    """Document JSON -> records shaped like the export, for evaluate.py."""
    text = g(doc, "text", default="") or ""
    pages = g(doc, "pages", default=[]) or []
    if not pages:
        return []
    page = pages[0]
    out, table_boxes = [], []
    for t in g(page, "tables", default=[]) or []:
        box = bbox_pt(g(t, "layout", default={}), w_pt, h_pt)
        grid = []
        for row in (g(t, "headerRows", "header_rows", []) or []) + \
                   (g(t, "bodyRows", "body_rows", []) or []):
            cells = row_cells(text, row)
            if cells:
                grid.append(cells)
        if not grid or box is None:
            continue
        table_boxes.append(box)
        width = max(len(r) for r in grid)
        grid = [r + [""] * (width - len(r)) for r in grid]
        out.append({"block_type": "Table", "bbox": box, "text": None,
                    "table": {"rows": grid, "raw_cells": grid}})
    for line in g(page, "lines", default=[]) or []:
        layout = g(line, "layout", default={})
        box = bbox_pt(layout, w_pt, h_pt)
        s = anchor_text(text, layout)
        if not s or box is None:
            continue
        # text inside a table is already in the table's grid
        if any(inside(box, tb) for tb in table_boxes):
            continue
        out.append({"block_type": "Text", "bbox": box, "text": s, "table": None})
    return out


def call_api(png):
    from google.api_core.client_options import ClientOptions
    from google.cloud import documentai

    project = os.environ["GCP_PROJECT"]
    location = os.environ.get("GCP_LOCATION", "us")
    processor = os.environ["GCP_PROCESSOR_ID"]
    client = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com"))
    name = client.processor_path(project, location, processor)
    result = client.process_document(request=documentai.ProcessRequest(
        name=name, raw_document=documentai.RawDocument(content=png, mime_type="image/png")))
    doc = json.loads(documentai.Document.to_json(result.document))
    for p in g(doc, "pages", default=[]) or []:
        p.pop("image", None)  # the page image itself is not needed in the cache
    try:
        version = client.get_processor(name=name).default_processor_version
    except Exception:
        version = "unknown"
    meta = {"processor": "form-parser", "processor_version": version, "location": location,
            "called": datetime.date.today().isoformat()}
    return doc, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--call", action="store_true", help="allow API calls on a cache miss")
    ap.add_argument("--params", default=str(ROOT / "params.yaml"))
    args = ap.parse_args()

    params = yaml.safe_load(open(args.params, encoding="utf-8"))
    dpi = tx.settings(params)["dpi"]
    gt_dir = ROOT / params["evaluate"]["gt_dir"]
    CACHE.mkdir(parents=True, exist_ok=True)

    summary = {}
    for stem, pdf, page in PAGES:
        png = tx.render_page_png(pdf, page, dpi)
        h = tx.page_hash(png)
        path = CACHE / f"{h}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            status = "cache"
        elif args.call:
            doc, meta = call_api(png)
            meta.update({"stem": stem, "page": page, "dpi": dpi})
            payload = {"meta": meta, "document": doc}
            path.write_text(json.dumps(payload), encoding="utf-8")
            status = "api"
        else:
            print(f"{stem}\tp{page}\tmiss\t{h}")
            continue

        w_pt, h_pt = tx.page_size_pt(pdf, page)
        recs = records_from_document(payload["document"], w_pt, h_pt)
        key = f"{stem}_p{page}"
        entry = {"cache": f"reports/gcp/{h}.json", "records": len(recs)}

        gt_txt = gt_dir / f"{key}.gt.txt"
        if gt_txt.exists():
            m = ev.text_metrics(gt_txt.read_text(encoding="utf-8"), ev.page_text(recs))
            entry.update(wer=m["wer"], cer=m["cer"], numeric_f1=m["numeric"]["f1"])

        gt_csv = gt_dir / f"{key}_t1.gt.csv"
        if gt_csv.exists():
            gt = ev.load_gt_table(gt_csv)
            hcr = set()
            for rec in ev.table_records(recs):
                _, cr, _ = ev.parser_table_cells(rec, gt["headings"])
                hcr |= cr
            entry["cell_raw"] = ev.prf(gt["cells_raw"], hcr)
            entry["tables_found"] = len(ev.table_records(recs))

        summary[key] = entry
        print(f"{key}\t{status}\twer {entry.get('wer')}\tcer {entry.get('cer')}\t"
              f"numeric_f1 {entry.get('numeric_f1')}\t"
              f"cell_raw_f1 {entry.get('cell_raw', {}).get('f1')}\t"
              f"tables {entry.get('tables_found')}")

    (CACHE / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()