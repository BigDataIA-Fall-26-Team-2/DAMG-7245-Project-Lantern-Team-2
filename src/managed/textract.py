"""Part 7: managed document AI (AWS Textract) as an optional fallback.

Two entry points:

  python -m managed.textract            run the configured pages, write the cache
  fallback_blocks(...)                  called from a parsing or table stage

Everything is cached by page-image hash in data/managed/. With
managed.enabled: false (the default) this module reads cache hits and makes no
API call, so the pipeline runs with no AWS credentials. That is what makes
`dvc repro` work in the grading environment.

The cache key is the sha256 of the rendered page image, not the file name or
page number. A re-render that produces identical pixels is a cache hit and
costs nothing; a re-render that genuinely changes the page is a miss, which is
the behaviour you want from a paid API.

Configuration always comes from the caller. A stage that was run with
--params passes its own params dict to fallback_blocks(); nothing here reads
params.yaml on import, so the switch the caller passed is the switch that
applies. Only the command line entry point reads a params file, and it takes
--params too.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema import Block  # noqa: E402

RENDERED = Path("data/rendered")


def load_params(path="params.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def settings(params):
    """The managed.* settings from the params dict the caller passed."""
    cfg = (params or {}).get("managed", {}) or {}
    return {
        "cfg": cfg,
        "cache_dir": Path(cfg.get("cache_dir", "data/managed")),
        "region": cfg.get("region", "us-east-1"),
        "features": list(cfg.get("features", ["TABLES", "LAYOUT"])),
        "dpi": int(cfg.get("dpi", 150)),
        # off unless the passed config explicitly turns it on
        "enabled": bool(cfg.get("enabled", False)),
    }

# Textract LAYOUT block types mapped onto the Appendix B vocabulary.
LAYOUT_TO_BLOCK_TYPE = {
    "LAYOUT_TITLE": "Title",
    "LAYOUT_SECTION_HEADER": "Title",
    "LAYOUT_HEADER": "Text",
    "LAYOUT_FOOTER": "Footnote",
    "LAYOUT_TEXT": "Text",
    "LAYOUT_LIST": "List",
    "LAYOUT_FIGURE": "Figure",
    "LAYOUT_TABLE": "Table",
    "LAYOUT_KEY_VALUE": "Text",
    "LAYOUT_PAGE_NUMBER": "Footnote",
}


# --- page rendering and hashing ------------------------------------------

def render_page_png(pdf_path, page, dpi=150):
    """One page of a PDF as PNG bytes, via pdftoppm.

    Textract's synchronous AnalyzeDocument takes a single page, so the page is
    rasterised rather than the whole PDF being uploaded.
    """
    with tempfile.TemporaryDirectory() as td:
        stem = str(Path(td) / "p")
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", "-f", str(page), "-l",
             str(page), str(pdf_path), stem],
            check=True, capture_output=True,
        )
        out = sorted(Path(td).glob("p-*.png"))
        if not out:
            raise FileNotFoundError(f"pdftoppm produced nothing for {pdf_path} p{page}")
        return out[0].read_bytes()


def page_hash(image_bytes):
    return hashlib.sha256(image_bytes).hexdigest()[:32]


def page_size_pt(pdf_path, page):
    """Page width and height in PDF points, for de-normalising Textract boxes."""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        p = pdf.pages[page - 1]
        return float(p.width), float(p.height)


# --- cache ----------------------------------------------------------------

def cache_path(h, cache_dir):
    return Path(cache_dir) / f"{h}.json"


def cached(h, cache_dir):
    p = cache_path(h, cache_dir)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def store(h, response, meta, cache_dir):
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "response": response}
    cache_path(h, cache_dir).write_text(json.dumps(payload), encoding="utf-8")


# --- the API call ---------------------------------------------------------

def analyze(image_bytes, region, features):
    """Call Textract. Only reached on a cache miss with managed.enabled true."""
    import boto3
    client = boto3.client("textract", region_name=region)
    return client.analyze_document(
        Document={"Bytes": image_bytes},
        FeatureTypes=features,
    )


def get_response(pdf_path, page, s, enabled=None):
    """Cache-first. Returns (response, hash, from_cache) or (None, hash, False).

    s is settings(params) from the caller. Never calls the API when the passed
    config is disabled, so a run without credentials still produces every
    record that is already cached.
    """
    if enabled is None:
        enabled = s["enabled"]
    img = render_page_png(pdf_path, page, s["dpi"])
    h = page_hash(img)
    hit = cached(h, s["cache_dir"])
    if hit is not None:
        return hit["response"], h, True
    if not enabled:
        return None, h, False
    resp = analyze(img, s["region"], s["features"])
    store(h, resp, {"source": str(pdf_path), "page": page, "dpi": s["dpi"],
                    "features": s["features"], "region": s["region"]},
          s["cache_dir"])
    return resp, h, False


# --- mapping into the Appendix B schema ----------------------------------

def _text_of(block, by_id):
    """Textract nests text: a LAYOUT or CELL block points at LINE/WORD ids."""
    if block.get("Text"):
        return block["Text"]
    parts = []
    for rel in block.get("Relationships", []) or []:
        if rel["Type"] != "CHILD":
            continue
        for cid in rel["Ids"]:
            child = by_id.get(cid)
            if not child:
                continue
            if child["BlockType"] in ("LINE", "WORD"):
                parts.append(child.get("Text", ""))
            else:
                t = _text_of(child, by_id)
                if t:
                    parts.append(t)
    return " ".join(p for p in parts if p).strip()


def _bbox_pt(geom, w_pt, h_pt):
    """Textract boxes are fractions of the page, top-left origin."""
    b = geom["BoundingBox"]
    x0 = b["Left"] * w_pt
    y0 = b["Top"] * h_pt
    return [round(x0, 2), round(y0, 2),
            round(x0 + b["Width"] * w_pt, 2),
            round(y0 + b["Height"] * h_pt, 2)]


def _table_payload(table, by_id):
    """TABLE block -> the schema's table object, via its CELL children."""
    cells = {}
    max_r = max_c = 0
    for rel in table.get("Relationships", []) or []:
        if rel["Type"] != "CHILD":
            continue
        for cid in rel["Ids"]:
            c = by_id.get(cid)
            if not c or c["BlockType"] != "CELL":
                continue
            r, col = c["RowIndex"], c["ColumnIndex"]
            max_r, max_c = max(max_r, r), max(max_c, col)
            cells[(r, col)] = _text_of(c, by_id)
    if not cells:
        return None
    raw = [[cells.get((r, c), "") for c in range(1, max_c + 1)]
           for r in range(1, max_r + 1)]
    columns = [""] + [f"col{c}" for c in range(1, max_c)]
    return {"columns": columns, "rows": raw, "raw_cells": raw, "scale": None}


def blocks_from_response(manifest_row, page, response, w_pt, h_pt, version):
    """Textract response -> validated schema Blocks.

    LAYOUT blocks give the reading structure; TABLE blocks give the grids.
    LAYOUT_TABLE blocks are skipped so a table is not emitted twice.
    """
    raw = response.get("Blocks", [])
    by_id = {b["Id"]: b for b in raw}
    out = []
    n = 0

    def base(block_type, bbox, text, table):
        nonlocal n
        n += 1
        rec = {
            "schema": "lantern/1.0",
            "doc_id": manifest_row["accession"],
            "company": manifest_row["company"],
            "cik": manifest_row["cik"],
            "ticker": manifest_row["ticker"],
            "form": manifest_row["form"],
            "fiscal_year": manifest_row["fiscal_year"],
            "fiscal_period": manifest_row["fiscal_period"],
            "page": page,
            "section": None,
            # Schema requires p{NNNN}_b{NNN}. Managed blocks use b500-b899:
            # layout blocks start at b001 and table blocks at b901, so the
            # extractor is recognisable from the id and nothing collides.
            "block_id": f"p{page:04d}_b{500 + n:03d}",
            "block_type": block_type,
            "bbox": bbox,
            "units": "pt",
            "origin": "top-left",
            "text": text,
            "table": table,
            "extractor": "aws-textract",
            "extractor_version": version,
            "ocr": True,
            "ocr_conf": None,
        }
        return rec

    for b in raw:
        bt = b["BlockType"]
        if bt in LAYOUT_TO_BLOCK_TYPE and bt != "LAYOUT_TABLE":
            text = _text_of(b, by_id)
            if not text:
                continue
            rec = base(LAYOUT_TO_BLOCK_TYPE[bt],
                       _bbox_pt(b["Geometry"], w_pt, h_pt), text, None)
            conf = b.get("Confidence")
            rec["ocr_conf"] = round(conf / 100.0, 4) if conf is not None else 0.0
            out.append(Block.model_validate(rec))
        elif bt == "TABLE":
            payload = _table_payload(b, by_id)
            if payload is None:
                continue
            rec = base("Table", _bbox_pt(b["Geometry"], w_pt, h_pt), None, payload)
            conf = b.get("Confidence")
            rec["ocr_conf"] = round(conf / 100.0, 4) if conf is not None else 0.0
            out.append(Block.model_validate(rec))
    return out


def service_version():
    try:
        from importlib.metadata import version
        return f"boto3 {version('boto3')}"
    except Exception:
        return "boto3"


# --- the hook a parsing or table stage calls -----------------------------

def fallback_blocks(manifest_row, pdf_path, page, reason="", params=None):
    """Managed fallback for one page. Returns [] when there is nothing to give.

    Call site contract, for Parts 1 and 2: fire this when your own confidence
    is low (mean OCR confidence below managed.trigger.min_ocr_conf, or a table
    score below managed.trigger.min_table_score). It returns schema-valid
    Blocks, or an empty list if the page is not cached and the service is
    disabled. It never raises on a missing cache and never calls the API
    unless managed.enabled is true, so it is safe to leave wired in.

    params is the caller's own params dict (the one its --params loaded). It
    decides the switch, the cache folder and the API settings. If no params
    are passed the service stays off.
    """
    resp, h, from_cache = get_response(pdf_path, page, settings(params))
    if resp is None:
        return []
    w_pt, h_pt = page_size_pt(pdf_path, page)
    blocks = blocks_from_response(manifest_row, page, resp, w_pt, h_pt,
                                  service_version())
    return blocks


# --- CLI ------------------------------------------------------------------

def load_manifest(params=None, path="data/rendered/manifest.csv"):
    import csv
    rows = {}
    company_by_ticker = ((params or {}).get("export", {}) or {}).get(
        "company_by_ticker", {})
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            form, period = row["form"], row["period"]
            rows[row["stem"]] = {
                "stem": row["stem"],
                "accession": row["accession"],
                "cik": row["cik"],
                "ticker": row["ticker"],
                "form": form,
                "period": period,
                "company": company_by_ticker.get(row["ticker"], row["ticker"]),
                "fiscal_year": int(period[:4]),
                "fiscal_period": "FY" if form.upper().replace("-", "") == "10K" else "Q",
            }
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--enable", action="store_true",
                    help="allow API calls on a cache miss (overrides params)")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    params = load_params(args.params)
    s = settings(params)
    manifest = load_manifest(params)
    pages = s["cfg"].get("pages", {}) or {}
    fixtures = s["cfg"].get("fixture_pages", {}) or {}
    enabled = True if args.enable else s["enabled"]

    by_stem = {}
    rows = []

    def run(stem, row, pdf, page_list):
        for page in page_list:
            resp, h, hit = get_response(pdf, page, s, enabled)
            if resp is None:
                rows.append((stem, page, "miss", h))
                continue
            w_pt, h_pt = page_size_pt(pdf, page)
            blocks = blocks_from_response(row, page, resp, w_pt, h_pt,
                                          service_version())
            by_stem.setdefault(stem, []).extend(blocks)
            rows.append((stem, page, "cache" if hit else "api",
                         f"{h} {len(blocks)} blocks"))

    for stem, page_list in pages.items():
        row = manifest.get(stem)
        if row is None:
            rows.append((stem, 0, "skip", "not in manifest"))
            continue
        run(stem, row, RENDERED / f"{stem}.pdf", page_list)

    for name, page_list in fixtures.items():
        pdf = Path("tests/fixtures") / f"{name}.pdf"
        if not pdf.exists():
            rows.append((name, 0, "skip", f"missing {pdf}"))
            continue
        # A fixture is not an SEC filing and has no accession number. The
        # schema requires one, so it gets an all-zero id in the valid format:
        # unmistakably synthetic, never confusable with a real filing.
        row = {"stem": name, "accession": "0000000000-00-000001",
               "cik": "0000000000", "ticker": "FIXT", "form": "10-K",
               "company": "Fixture", "fiscal_year": 2025,
               "fiscal_period": "FY"}
        run(name, row, pdf, page_list)

    # one file per document, named like the export stage's, so the evaluate
    # stage can read the managed path the same way it reads the others
    out_dir = Path(args.out_dir or s["cache_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for stem, blocks in by_stem.items():
        path = out_dir / f"{stem}.blocks.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for b in sorted(blocks, key=lambda b: (b.page, b.bbox[1], b.bbox[0])):
                f.write(b.to_jsonl() + "\n")
        total += len(blocks)

    for stem, page, status, detail in rows:
        print(f"{stem}\tp{page}\t{status}\t{detail}")
    print(f"{out_dir}\t{total}")


if __name__ == "__main__":
    main()