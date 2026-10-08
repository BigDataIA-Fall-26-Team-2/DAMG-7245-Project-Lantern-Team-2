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
    "doc_id", "accession", "cik", "source_file", "ticker", "form", "period", "stem", "pdf_path",
    "renderer", "renderer_version", "page_width_pt", "page_height_pt",
]


def main(params_path: str, input_dir: str, output: str) -> None:
    config = yaml.safe_load(Path(params_path).read_text())
    params = config["render"]
    page_format = params["page_format"]

    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)

    filing_dirs = sorted(Path(input_dir).glob("sec-edgar-filings/*/*/*/"))
    if not filing_dirs:
        raise RuntimeError(f"no filings found under {input_dir} — run src/download.py first")

    expected_dirs = {
        Path(input_dir) / "sec-edgar-filings" / config["download"]["ticker"] / form / filing["accession"]
        for form, filing in config["download"]["filings"].items()
    }
    if set(filing_dirs) != expected_dirs:
        raise ValueError("render input does not match params.yaml pinned filings")
    expected_stems = {
        stem_for({"ticker": config["download"]["ticker"], "form": form, "period": filing["period"]})
        for form, filing in config["download"]["filings"].items()
    }
    if {p.stem for p in out_dir.glob("*.pdf")} - expected_stems:
        raise ValueError("render output contains stale PDFs; archive it and use a clean output directory")

    with sync_playwright() as pw, (out_dir / "manifest.csv").open("w", newline="") as f:
        browser = pw.chromium.launch()
        page = browser.new_page()
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()

        for filing_dir in filing_dirs:
            meta = json.loads((filing_dir / "unpacked" / "meta.json").read_text())
            pinned = config["download"]["filings"][filing_dir.parent.name]
            if (meta["accession"] != pinned["accession"] or meta["period"] != pinned["period"]
                    or meta["form"] != filing_dir.parent.name or meta["ticker"] != config["download"]["ticker"]):
                raise ValueError(f"{filing_dir}: metadata does not match pinned filing")
            source_file = filing_dir / "unpacked" / meta["source_file"]
            if not source_file.is_file():
                raise RuntimeError(f"{source_file}: missing unpacked primary document; rerun download")

            stem = stem_for(meta)
            pdf_path = out_dir / f"{stem}.pdf"
            page.goto(source_file.resolve().as_uri())
            broken_images = page.evaluate("""async () => {
                const images = Array.from(document.images);
                await Promise.allSettled(images.map(image => image.decode()));
                return images.filter(image => !image.complete || image.naturalWidth === 0)
                             .map(image => image.getAttribute('src'));
            }""")
            if broken_images:
                raise RuntimeError(f"{source_file}: failed to load images {broken_images}; rerun download")
            page.pdf(path=str(pdf_path), format=page_format)

            # Read the page size back from the PDF itself — a filing's own CSS can override
            # the requested format/orientation, so the requested format isn't ground truth.
            pdf_page = PdfReader(pdf_path).pages[0]

            writer.writerow({
                "doc_id": meta["accession"],
                "accession": meta["accession"],
                "cik": meta["cik"],
                "source_file": str(source_file),
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
