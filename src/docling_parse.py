"""Stage: parse_docling. Docling conversion and exports (Part 4: the alternative path to the traditional pipeline).

Reads params.yaml:docling, data/rendered/*.pdf and data/rendered/manifest.csv. Writes, per filing, to data/docling/:
  {stem}.md            full Markdown
  {stem}.json          lossless DoclingDocument JSON
  {stem}_p{NNNN}.md    one Markdown file per page (for per-page WER in Part 9)
  {stem}.blocks.jsonl  one record per item: page, block_id, block_type, bbox (points, top-left origin), text
"""
import argparse
import csv
import json
import time
from importlib.metadata import version
from pathlib import Path
import sys

# This file must be named docling_parse.py (Case Study Part 4), which is also the name of Docling's own
# parser package. Running `python src/docling_parse.py` puts src/ first on sys.path, so Docling's
# `import docling_parse` would load this file instead (circular import). Drop src/ before importing Docling.
_HERE = Path(__file__).resolve().parent
sys.path = [s for s in sys.path if Path(s or ".").resolve() != _HERE]

import yaml
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption

import docling_parse as _docling_parse_pkg  # noqa: F401  load Docling's real parser now, so later lazy imports reuse it
sys.path.insert(0, str(_HERE))              # safe now: src/ siblings can be imported again
import pandas as pd
import tables as tbl                        # P2 helpers: to_long, page_text_and_words, write_table_csv

MODEL = f"docling {version('docling')}"

# Docling's item labels -> the team block types (Case Study Appendix B)
TYPE_MAP = {"title": "Title", "section_header": "Title", "list_item": "List", "table": "Table",
            "picture": "Figure", "chart": "Figure", "footnote": "Footnote"}
FOOTER_LABELS = {"page_header", "page_footer"}


def load_params(path="params.yaml"):
    return yaml.safe_load(Path(path).read_text())


def load_manifest(input_dir):
    """stem -> manifest row (doc_id, source_file, ...), from the render manifest; empty for folders without one (e.g. fixtures)."""
    path = Path(input_dir) / "manifest.csv"
    if not path.exists():
        return {}
    with open(path, newline="") as f:
        return {r["stem"]: r for r in csv.DictReader(f)}


def make_converter(p):
    """Docling PDF converter with OCR and TableFormer mode taken from params.yaml:docling."""
    opts = PdfPipelineOptions(do_ocr=p["do_ocr"], do_table_structure=True)
    opts.table_structure_options.mode = (TableFormerMode.ACCURATE if p["table_mode"] == "accurate"
                                         else TableFormerMode.FAST)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def clear_outputs(stem, out, html=False):
    """Delete one filing's outputs from earlier runs before regenerating them.

    Without this, fewer tables, a table that no longer normalizes, or a shorter document would leave stale
    files that downstream stages (P9, P11) read as current. Only files for this stem are touched."""
    if html:
        paths = [out / f"{stem}.html.md", out / f"{stem}.html.json", *out.glob(f"{stem}_html_t*_raw.csv")]
    else:
        paths = [out / f"{stem}.md", out / f"{stem}.json", out / f"{stem}.blocks.jsonl",
                 *out.glob(f"{stem}_p*.md"), *out.glob(f"{stem}_p*_t*_raw.csv"),
                 *(out / "tables").glob(f"{stem}_p*_t*.csv")]
    removed = 0
    for path in paths:
        if path.exists():
            path.unlink()
            removed += 1
    return removed


def export_document(doc, stem, out):
    """Write full Markdown, lossless JSON, and one Markdown file per page. Returns the page count."""
    (out / f"{stem}.md").write_text(doc.export_to_markdown())
    doc.save_as_json(out / f"{stem}.json")
    for n in sorted(doc.pages):
        (out / f"{stem}_p{n:04d}.md").write_text(doc.export_to_markdown(page_no=n))
    return len(doc.pages)


def crop_offsets(pdf_path):
    """Per page: (dx, dy) to add to Docling boxes to move them into the team frame.

    Docling measures boxes from the page's visible area (cropbox); pdfplumber, whose frame the team
    contract uses, measures from the full mediabox. The offset is where the cropbox starts inside the
    mediabox, in top-left display coordinates, which depends on the page's /Rotate. Zero when the
    cropbox equals the mediabox (all Apple pages)."""
    from pypdf import PdfReader
    offsets = {}
    for i, pg in enumerate(PdfReader(str(pdf_path)).pages, start=1):
        m, c = pg.mediabox, pg.cropbox
        mx0, my0, mx1, my1 = (float(v) for v in (m.left, m.bottom, m.right, m.top))
        cx0, cy0, cx1, cy1 = (float(v) for v in (c.left, c.bottom, c.right, c.top))
        rot = (pg.rotation or 0) % 360
        if rot == 0:
            offsets[i] = (cx0 - mx0, my1 - cy1)
        elif rot == 90:
            offsets[i] = (cy0 - my0, cx0 - mx0)
        elif rot == 180:
            offsets[i] = (mx1 - cx1, cy0 - my0)
        else:  # 270
            offsets[i] = (my1 - cy1, mx1 - cx1)
    return offsets


def export_blocks(doc, stem, doc_id, out, offsets):
    """One JSONL record per Docling item, in Docling's reading order, with bbox converted to top-left origin."""
    per_page, counts = {}, {}
    with open(out / f"{stem}.blocks.jsonl", "w") as f:
        for item, _level in doc.iterate_items():
            if not getattr(item, "prov", None):
                continue                                   # groups and other items without a page location
            prov = item.prov[0]
            n = prov.page_no
            page_h = doc.pages[n].size.height
            bb = prov.bbox.to_top_left_origin(page_height=page_h)   # Docling default is bottom-left
            dx, dy = offsets.get(n, (0.0, 0.0))              # cropbox -> mediabox frame
            label = str(getattr(item.label, "value", item.label))
            block_type = TYPE_MAP.get(label, "Text")
            per_page[n] = per_page.get(n, 0) + 1
            rec = {"doc_id": doc_id, "page": n, "block_id": f"p{n:04d}_b{per_page[n]:03d}",
                   "block_type": block_type, "docling_label": label,
                   "bbox": [round(bb.l + dx, 2), round(bb.t + dy, 2), round(bb.r + dx, 2), round(bb.b + dy, 2)],
                   "units": "pt", "origin": "top-left", "model": MODEL,
                   "text": getattr(item, "text", None), "footer": label in FOOTER_LABELS}
            f.write(json.dumps(rec) + "\n")
            counts[block_type] = counts.get(block_type, 0) + 1
    return counts


def export_tables(doc, stem, pdf_path, out):
    """Every Docling table as (a) its raw Docling CSV and (b) team-format rows via the P2 normalizer.

    The team-format file goes through tables.to_long with the FULL page text, so number cleaning, scale
    ("in millions"), per-share handling and period labels match the traditional path exactly; only the
    table structure and numbers come from Docling."""
    tdir = out / "tables"
    tdir.mkdir(parents=True, exist_ok=True)
    per_page, written, empty = {}, 0, 0
    for table in doc.tables:
        if not table.prov:
            continue
        n = table.prov[0].page_no
        per_page[n] = per_page.get(n, 0) + 1
        k = per_page[n]
        df = table.export_to_dataframe(doc=doc)
        df.to_csv(out / f"{stem}_p{n:04d}_t{k}_raw.csv", index=False)
        grid = pd.DataFrame([[str(c) for c in df.columns]] + df.astype(str).values.tolist())
        text, words = tbl.page_text_and_words(str(pdf_path), n)
        rows, _skipped = tbl.to_long(grid, text, words)
        if not rows:
            empty += 1
            continue
        tbl.write_table_csv(rows, tdir / f"{stem}_p{n:04d}_t{k}.csv")
        written += 1
    return written, empty


def convert_html(conv, row, out):
    """Part 4 task 2: also convert the filing's original iXBRL HTML, to isolate what PDF rendering changed.

    HTML has no pages, so there are no page numbers or boxes: only text and tables can be compared."""
    stem = row["stem"]
    clear_outputs(stem, out, html=True)
    t = time.perf_counter()
    doc = conv.convert(row["source_file"]).document
    md = doc.export_to_markdown()
    (out / f"{stem}.html.md").write_text(md)
    doc.save_as_json(out / f"{stem}.html.json")
    for k, table in enumerate(doc.tables, start=1):
        table.export_to_dataframe(doc=doc).to_csv(out / f"{stem}_html_t{k}_raw.csv", index=False)
    print(f"{stem} (original HTML): {len(doc.tables)} tables, {len(md)} chars, {time.perf_counter() - t:.1f}s")


def main(params_path, input_dir, output):
    p = load_params(params_path)["docling"]
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(input_dir)
    conv = make_converter(p)
    for pdf_path in sorted(Path(input_dir).glob("*.pdf")):
        stem = pdf_path.stem
        t = time.perf_counter()
        doc = conv.convert(str(pdf_path)).document
        clear_outputs(stem, out)
        n_pages = export_document(doc, stem, out)
        counts = export_blocks(doc, stem, manifest.get(stem, {}).get("doc_id", stem), out, crop_offsets(pdf_path))
        written, empty = export_tables(doc, stem, pdf_path, out)
        print(f"{stem}: {n_pages} pages, {len(doc.tables)} tables ({written} in team format, {empty} empty), blocks {counts}, {time.perf_counter() - t:.1f}s")
    if p.get("html_stem") in manifest:   # skipped for folders without a manifest (fixtures)
        convert_html(conv, manifest[p["html_stem"]], out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--input", default="data/rendered")
    ap.add_argument("--output", default="data/docling")
    a = ap.parse_args()
    main(a.params, a.input, a.output)
