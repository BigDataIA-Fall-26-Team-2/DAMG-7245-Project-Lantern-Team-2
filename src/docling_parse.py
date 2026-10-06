"""Stage: parse_docling. Docling conversion and exports (Part 4: the alternative path to the traditional pipeline).

Reads params.yaml:docling and data/rendered/*.pdf. Writes, per filing, to data/docling/:
  {stem}.md            full Markdown
  {stem}.json          lossless DoclingDocument JSON
  {stem}_p{NNNN}.md    one Markdown file per page (for per-page WER in Part 9)
"""
import argparse
import time
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


def load_params(path="params.yaml"):
    return yaml.safe_load(Path(path).read_text())


def make_converter(p):
    """Docling PDF converter with OCR and TableFormer mode taken from params.yaml:docling."""
    opts = PdfPipelineOptions(do_ocr=p["do_ocr"], do_table_structure=True)
    opts.table_structure_options.mode = (TableFormerMode.ACCURATE if p["table_mode"] == "accurate"
                                         else TableFormerMode.FAST)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def export_document(doc, stem, out):
    """Write full Markdown, lossless JSON, and one Markdown file per page. Returns the page count."""
    (out / f"{stem}.md").write_text(doc.export_to_markdown())
    doc.save_as_json(out / f"{stem}.json")
    for n in sorted(doc.pages):
        (out / f"{stem}_p{n:04d}.md").write_text(doc.export_to_markdown(page_no=n))
    return len(doc.pages)


def main(params_path, input_dir, output):
    p = load_params(params_path)["docling"]
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    conv = make_converter(p)
    for pdf_path in sorted(Path(input_dir).glob("*.pdf")):
        t = time.perf_counter()
        doc = conv.convert(str(pdf_path)).document
        n_pages = export_document(doc, pdf_path.stem, out)
        print(f"{pdf_path.stem}: {n_pages} pages, {len(doc.tables)} tables, {time.perf_counter() - t:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--input", default="data/rendered")
    ap.add_argument("--output", default="data/docling")
    a = ap.parse_args()
    main(a.params, a.input, a.output)
