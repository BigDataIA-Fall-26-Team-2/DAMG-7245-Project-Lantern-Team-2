"""TXT baseline export (Part 6, issue #58).

Writes data/export/{stem}.txt: the plain text of every page in reading order (pdfplumber
`extract_text`), pages separated by a form feed (\\f), with no structure or provenance.
This is the baseline the Markdown and JSONL formats are compared against.

Run:  python src/export_txt.py --input data/rendered --output data/export
"""
import argparse
import csv
from pathlib import Path

import pdfplumber


def page_texts(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        return [(p.extract_text() or "").strip() for p in pdf.pages]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plain-text baseline export")
    ap.add_argument("--input", default="data/rendered", help="folder with manifest.csv and the PDFs")
    ap.add_argument("--output", default="data/export", help="folder for {stem}.txt")
    a = ap.parse_args(argv)
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    with open(Path(a.input) / "manifest.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        texts = page_texts(row["pdf_path"])
        target = out / f"{row['stem']}.txt"
        tmp = target.with_suffix(".txt.tmp")
        tmp.write_text("\n\f\n".join(texts) + "\n", encoding="utf-8")
        tmp.replace(target)
        print(f"{row['stem']}\t{len(texts)} pages\t{target.stat().st_size} bytes")


if __name__ == "__main__":
    main()
