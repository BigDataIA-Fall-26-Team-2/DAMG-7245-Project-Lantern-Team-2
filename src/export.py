import csv
import glob
import json
import re
from pathlib import Path
import yaml

from adapters import (
    block_from_layout_record,
    block_from_docling_record,
    table_from_csv_rows,
)

PARAMS = yaml.safe_load(open("params.yaml", encoding="utf-8"))
EXPORT = PARAMS.get("export", {})

MANIFEST = Path("data/rendered/manifest.csv")
LAYOUT_DIR = Path(EXPORT.get("layout_dir", "data/layout"))
DOCLING_DIR = Path(EXPORT.get("docling_dir", "data/docling"))
TABLES_DIR = Path(EXPORT.get("tables_dir", "data/tables"))
EXPORT_DIR = Path(EXPORT.get("out_dir", "data/export"))

PARAGRAPH_GAP_PT = float(EXPORT.get("paragraph_gap_pt", 6.0))
EMIT_DOCLING = bool(EXPORT.get("emit_docling", True))
COMPANY_BY_TICKER = EXPORT.get("company_by_ticker", {})

ITEM_RE = re.compile(r"^Item\s+\d+[A-Z]?\.?", re.IGNORECASE)


def load_manifest(path=MANIFEST):
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            form = row["form"]
            period = row["period"]
            rows[row["stem"]] = {
                "stem": row["stem"],
                "accession": row["accession"],
                "cik": row["cik"],
                "ticker": row["ticker"],
                "form": form,
                "period": period,
                "source_file": row["source_file"],
                "company": COMPANY_BY_TICKER.get(row["ticker"], row["ticker"]),
                "fiscal_year": int(period[:4]),
                "fiscal_period": "FY" if form.upper().replace("-", "") == "10K" else "Q",
            }
    return rows


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def section_for(text, current):
    if text and ITEM_RE.match(text.strip()):
        return text.strip().split(".")[0].strip()
    return current


def layout_blocks(manifest_row, stem):
    path = LAYOUT_DIR / f"{stem}.blocks.jsonl"
    blocks, section = [], None
    table_bbox = {}
    for rec in read_jsonl(path):
        if rec["block_type"] == "Table":
            table_bbox.setdefault(rec["page"], []).append(rec["bbox"])
            continue
        section = section_for(rec.get("text"), section)
        b = block_from_layout_record(manifest_row, rec, section)
        if b is not None:
            blocks.append(b)
    return blocks, table_bbox


def table_blocks(manifest_row, stem, table_bbox):
    blocks = []
    paths = sorted(glob.glob(str(TABLES_DIR / f"{stem}_p*_t*.csv")))
    page_counts = {}
    for p in paths:
        pg = int(re.search(r"_p(\d+)_", Path(p).stem).group(1))
        page_counts[pg] = page_counts.get(pg, 0) + 1
    for csv_path in paths:
        name = Path(csv_path).stem
        page = int(re.search(r"_p(\d+)_", name).group(1))
        tk = int(re.search(r"_t(\d+)$", name).group(1))
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        boxes = table_bbox.get(page, [])
        page_tables = page_counts.get(page, 0)
        if len(boxes) == page_tables and tk <= len(boxes):
            bbox = boxes[tk - 1]
        elif boxes:
            bbox = [
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            ]
        else:
            bbox = [0.0, 0.0, 1.0, 1.0]
        block_id = f"p{page:04d}_b{900 + tk:03d}"
        scale = rows[0].get("scale")
        blocks.append(table_from_csv_rows(manifest_row, page, block_id, bbox, rows, scale))
    return blocks


def docling_blocks(manifest_row, stem):
    path = DOCLING_DIR / f"{stem}.blocks.jsonl"
    blocks, section = [], None
    for rec in read_jsonl(path):
        if rec["block_type"] == "Table":
            continue
        section = section_for(rec.get("text"), section)
        b = block_from_docling_record(manifest_row, rec, section)
        if b is not None:
            blocks.append(b)
    return blocks


def reading_order(blocks):
    return sorted(blocks, key=lambda b: (b.page, b.bbox[1], b.bbox[0]))


def write_jsonl(blocks, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for b in reading_order(blocks):
            f.write(b.to_jsonl() + "\n")


def main():
    manifest = load_manifest()
    for stem, row in manifest.items():
        trad, table_bbox = layout_blocks(row, stem)
        trad += table_blocks(row, stem, table_bbox)
        write_jsonl(trad, EXPORT_DIR / f"{stem}.jsonl")
        doc = []
        if EMIT_DOCLING:
            doc = docling_blocks(row, stem)
            write_jsonl(doc, EXPORT_DIR / f"{stem}.docling.jsonl")
        print(f"{stem}\ttraditional={len(trad)}\tdocling={len(doc)}")


if __name__ == "__main__":
    main()