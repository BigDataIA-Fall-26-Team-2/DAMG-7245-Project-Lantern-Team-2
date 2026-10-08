import csv
import glob
import json
import re
from pathlib import Path
import yaml
from export_txt import main as export_txt

from adapters import (
    block_from_layout_record,
    block_from_docling_record,
    table_from_csv_rows,
    table_methods,
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
    methods = table_methods()
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
        method = methods.get((stem, page))
        blocks.append(table_from_csv_rows(manifest_row, page, block_id, bbox, rows, method))
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

def table_to_markdown(t):
    lines = ["| " + " | ".join(str(c) for c in t.columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in t.columns) + " |")
    for row in t.rows:
        cells = ["" if c is None else str(c) for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def provenance_comment(b):
    fields = {
        "doc_id": b.doc_id,
        "page": b.page,
        "block_id": b.block_id,
        "block_type": b.block_type,
        "bbox": b.bbox,
        "units": b.units,
        "origin": b.origin,
        "extractor": b.extractor,
        "extractor_version": b.extractor_version,
        "ocr": b.ocr,
        "ocr_conf": b.ocr_conf,
    }
    return "<!-- " + json.dumps(fields, ensure_ascii=False) + " -->"


def block_to_markdown(b):
    if b.block_type == "Title":
        body = f"## {b.text}"
    elif b.block_type == "Table" and b.table is not None:
        body = table_to_markdown(b.table)
    elif b.block_type == "List":
        body = "\n".join(f"- {line}" for line in (b.text or "").split("\n") if line)
    elif b.block_type == "Footnote":
        body = f"> {b.text}"
    else:
        body = b.text or ""
    return provenance_comment(b) + "\n" + body


def write_markdown(blocks, path, manifest_row):
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = reading_order(blocks)
    head = [
        f"# {manifest_row['company']} {manifest_row['form']} "
        f"{manifest_row['fiscal_year']} {manifest_row['fiscal_period']}",
        "",
        provenance_comment(ordered[0]) if ordered else "",
    ]
    parts = [head[0], head[1]]
    current_page = None
    for b in ordered:
        if b.page != current_page:
            current_page = b.page
            parts.append(f"\n<!-- page {b.page} -->")
        parts.append(block_to_markdown(b))
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")    


def main():
    manifest = load_manifest()
    for stem, row in manifest.items():
        layout_path = LAYOUT_DIR / f"{stem}.blocks.jsonl"
        if layout_path.exists():
            trad, table_bbox = layout_blocks(row, stem)
            trad += table_blocks(row, stem, table_bbox)
            write_jsonl(trad, EXPORT_DIR / f"{stem}.jsonl")
            write_markdown(trad, EXPORT_DIR / f"{stem}.md", row)
        else:
            trad = []
            print(f"{stem}\tSKIPPED traditional: missing {layout_path} (run the layout stage, Part 3)")

        doc = []
        if EMIT_DOCLING:
            docling_path = DOCLING_DIR / f"{stem}.blocks.jsonl"
            if docling_path.exists():
                doc = docling_blocks(row, stem)
                write_jsonl(doc, EXPORT_DIR / f"{stem}.docling.jsonl")
            else:
                print(f"{stem}\tSKIPPED docling: missing {docling_path} (run the docling stage, Part 4)")

        print(f"{stem}\ttraditional={len(trad)}\tdocling={len(doc)}")

    export_txt(["--input", str(MANIFEST.parent), "--output", str(EXPORT_DIR)])


if __name__ == "__main__":
    main()
