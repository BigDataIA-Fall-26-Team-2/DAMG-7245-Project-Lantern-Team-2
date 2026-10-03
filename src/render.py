"""Render each downloaded filing's primary document to PDF and log a manifest.

Stage: render. Reads params.yaml:render and data/raw/. Writes data/rendered/.
"""
import argparse
import csv
import json
from importlib.metadata import version
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

from contracts import stem_for

MANIFEST_FIELDS = [
    "doc_id", "ticker", "form", "period", "stem", "pdf_path",
    "renderer", "renderer_version", "page_width_pt", "page_height_pt",
]


def main(params_path: str, input_dir: str, output: str) -> None:
    params = yaml.safe_load(Path(params_path).read_text())["render"]
    page_format = params["page_format"]

    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    filing_dirs = sorted(Path(input_dir).glob("sec-edgar-filings/*/*/*/"))
    if not filing_dirs:
        raise RuntimeError(f"no filings found under {input_dir} — run src/download.py first")

    with sync_playwright() as pw, (out_dir / "manifest.csv").open("w", newline="") as f:
        browser = pw.chromium.launch()
        page = browser.new_page()
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()

        for filing_dir in filing_dirs:
            meta = json.loads((filing_dir / "unpacked" / "meta.json").read_text())
            primary_docs = list(filing_dir.glob("primary-document.*"))
            if len(primary_docs) != 1:
                raise RuntimeError(f"{filing_dir}: expected one primary-document file, found {len(primary_docs)}")

            stem = stem_for(meta)
            pdf_path = out_dir / f"{stem}.pdf"
            page.goto(primary_docs[0].resolve().as_uri())
            page.pdf(path=str(pdf_path), format=page_format)

            # Read the page size back from the PDF itself — a filing's own CSS can override
            # the requested format/orientation, so the requested format isn't ground truth.
            pdf_page = PdfReader(pdf_path).pages[0]

            writer.writerow({
                "doc_id": meta["accession"],
                "ticker": meta["ticker"],
                "form": meta["form"],
                "period": meta["period"],
                "stem": stem,
                "pdf_path": str(pdf_path),
                "renderer": "playwright",
                "renderer_version": version("playwright"),
                "page_width_pt": float(pdf_page.mediabox.width),
                "page_height_pt": float(pdf_page.mediabox.height),
            })
            f.flush()
            print(f"rendered {stem}.pdf")

        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--params", default="params.yaml")
    parser.add_argument("--input", default="data/raw")
    parser.add_argument("--output", default="data/rendered")
    args = parser.parse_args()
    main(args.params, args.input, args.output)
