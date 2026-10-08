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
    table_methods,
)

PARAMS = yaml.safe_load(open("params.yaml", encoding="utf-8"))
EXPORT = PARAMS.get("export", {})

MANIFEST = Path("data/rendered/manifest.csv")
RENDERED_DIR = Path("data/rendered")
LAYOUT_DIR = Path(EXPORT.get("layout_dir", "data/layout"))
DOCLING_DIR = Path(EXPORT.get("docling_dir", "data/docling"))
TABLES_DIR = Path(EXPORT.get("tables_dir", "data/tables"))
EXPORT_DIR = Path(EXPORT.get("out_dir", "data/export"))
FALLBACK_LOG = Path(EXPORT.get("bbox_fallback_log",
                               "reports/export_bbox_fallback.csv"))

PARAGRAPH_GAP_PT = float(EXPORT.get("paragraph_gap_pt", 6.0))
EMIT_DOCLING = bool(EXPORT.get("emit_docling", True))
COMPANY_BY_TICKER = EXPORT.get("company_by_ticker", {})

ITEM_RE = re.compile(r"^Item\s+\d+[A-Z]?\.?", re.IGNORECASE)

DEFAULT_PAGE_PT = (612.0, 792.0)  # US Letter, only if the PDF is unavailable


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


def page_sizes(stem, rendered_dir=RENDERED_DIR):
    """Page width and height in points, read from the rendered PDF.

    Used only for the table bbox fallback below. The page box is a truthful
    statement that the table is somewhere on this page; it is deliberately not
    derived from other detected blocks, because those blocks are not the table
    and their union can be an arbitrarily small rectangle in the wrong place.
    """
    pdf = Path(rendered_dir) / f"{stem}.pdf"
    if not pdf.exists():
        return {}
    try:
        import pdfplumber
    except ImportError:
        return {}
    with pdfplumber.open(pdf) as doc:
        return {i + 1: (round(float(p.width), 2), round(float(p.height), 2))
                for i, p in enumerate(doc.pages)}


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


def table_bbox_for(page, tk, boxes, page_tables, sizes):
    """Choose a bbox for one table CSV, and say how precise the choice is.

    Returns (bbox, precision, note) where precision is one of:
      "detected" - paired one-to-one with a layout Table detection
      "union"    - several layout Table detections on the page, count disagrees
                   with the number of CSVs, so the box spans all of them; every
                   box in the union is a real table region
      "page"     - no layout Table detection on this page at all, so the box is
                   the whole page. Approximate, and logged.

    The "page" case must not be derived from the other detected blocks on the
    page: those are headings and paragraphs, not the table, and their union is
    a narrow rectangle pointing at the wrong region while looking precise.
    """
    if len(boxes) == page_tables and tk <= len(boxes):
        return boxes[tk - 1], "detected", ""
    if boxes:
        return [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ], "union", f"{len(boxes)} layout Table regions, {page_tables} table CSVs"
    w, h = sizes.get(page, DEFAULT_PAGE_PT)
    note = "no layout Table region on this page; bbox is the full page"
    if page not in sizes:
        note += " (rendered PDF unavailable, assumed US Letter)"
    return [0.0, 0.0, float(w), float(h)], "page", note


def table_blocks(manifest_row, stem, table_bbox, sizes):
    blocks, fallbacks = [], []
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
        bbox, precision, note = table_bbox_for(
            page, tk, table_bbox.get(page, []), page_counts.get(page, 0), sizes)
        block_id = f"p{page:04d}_b{900 + tk:03d}"
        if precision != "detected":
            fallbacks.append({
                "stem": stem, "page": page, "block_id": block_id,
                "precision": precision, "bbox": json.dumps(bbox), "note": note,
            })
        method = methods.get((stem, page))
        blocks.append(table_from_csv_rows(manifest_row, page, block_id, bbox,
                                          rows, method))
    return blocks, fallbacks


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


def write_fallback_log(rows, path=FALLBACK_LOG):
    """Every approximated table bbox, so the imprecision is visible.

    A wrong bbox is still a schema-valid bbox, so nothing downstream can
    detect this. It has to be recorded at the point the approximation is made.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["stem", "page", "block_id", "precision", "bbox", "note"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


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
    parts = [
        f"# {manifest_row['company']} {manifest_row['form']} "
        f"{manifest_row['fiscal_year']} {manifest_row['fiscal_period']}",
        "",
    ]
    current_page = None
    for b in ordered:
        if b.page != current_page:
            current_page = b.page
            parts.append(f"\n<!-- page {b.page} -->")
        parts.append(block_to_markdown(b))
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def main():
    manifest = load_manifest()
    all_fallbacks = []
    for stem, row in manifest.items():
        layout_path = LAYOUT_DIR / f"{stem}.blocks.jsonl"
        if layout_path.exists():
            trad, table_bbox = layout_blocks(row, stem)
            sizes = page_sizes(stem)
            tbl, fallbacks = table_blocks(row, stem, table_bbox, sizes)
            trad += tbl
            all_fallbacks += fallbacks
            write_jsonl(trad, EXPORT_DIR / f"{stem}.jsonl")
            write_markdown(trad, EXPORT_DIR / f"{stem}.md", row)
        else:
            trad = []
            print(f"{stem}\tSKIPPED traditional: missing {layout_path} "
                  f"(run the layout stage, Part 3)")

        doc = []
        if EMIT_DOCLING:
            docling_path = DOCLING_DIR / f"{stem}.blocks.jsonl"
            if docling_path.exists():
                doc = docling_blocks(row, stem)
                write_jsonl(doc, EXPORT_DIR / f"{stem}.docling.jsonl")
            else:
                print(f"{stem}\tSKIPPED docling: missing {docling_path} "
                      f"(run the docling stage, Part 4)")

        print(f"{stem}\ttraditional={len(trad)}\tdocling={len(doc)}")

    write_fallback_log(all_fallbacks)
    by_precision = {}
    for r in all_fallbacks:
        by_precision[r["precision"]] = by_precision.get(r["precision"], 0) + 1
    print(f"{FALLBACK_LOG}\t{by_precision}")


if __name__ == "__main__":
    main()