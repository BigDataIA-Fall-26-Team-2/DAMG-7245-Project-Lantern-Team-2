"""Part 2 table bake-off (#17): Camelot lattice/stream/network/hybrid vs pdfplumber 'text'.

Runs every method on each statement page, saves every extracted table as CSV,
and writes summary.csv with shape, Camelot parsing report, runtime and ruling counts.
"""
import argparse
import csv
import time
from pathlib import Path

import camelot
import pandas as pd
import pdfplumber

DEFAULT_PAGES = ("AAPL_10K_20250927:32:income,AAPL_10K_20250927:34:balance,"
                 "AAPL_10Q_20260627:4:income,AAPL_10Q_20260627:6:balance")
CAMELOT_FLAVORS = ["lattice", "stream", "network", "hybrid"]
FIELDS = ["stem", "page", "kind", "method", "status", "n_tables", "largest_shape",
          "accuracy", "whitespace", "seconds", "h_rulings", "v_rulings", "error"]


def count_rulings(page):
    """Horizontal/vertical rulings: drawn lines plus thin filled rects (Chromium table borders)."""
    h = sum(abs(l["top"] - l["bottom"]) < 1 for l in page.lines)
    h += sum(r["height"] < 2 and r["width"] > 10 for r in page.rects)
    v = sum(abs(l["x0"] - l["x1"]) < 1 for l in page.lines)
    v += sum(r["width"] < 2 and r["height"] > 10 for r in page.rects)
    return int(h), int(v)


def run_camelot(pdf_path, page_no, flavor):
    tables = camelot.read_pdf(str(pdf_path), pages=str(page_no), flavor=flavor)
    results = []
    for t in tables:
        report = t.parsing_report or {}
        results.append((t.df, report.get("accuracy"), report.get("whitespace")))
    return results


def run_pdfplumber_text(pdf_path, page_no):
    settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}
    with pdfplumber.open(pdf_path) as pdf:
        raw_tables = pdf.pages[page_no - 1].extract_tables(settings)
    return [(pd.DataFrame(rows), None, None) for rows in raw_tables]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="data/rendered", help="folder with rendered PDFs")
    ap.add_argument("--output", default="prototyping/dhruvi/bakeoff/results", help="results folder")
    ap.add_argument("--pages", default=DEFAULT_PAGES, help="comma-separated stem:page:kind")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for spec in args.pages.split(","):
        stem, page_s, kind = spec.split(":")
        page_no = int(page_s)
        pdf_path = Path(args.input) / f"{stem}.pdf"
        with pdfplumber.open(pdf_path) as pdf:
            h, v = count_rulings(pdf.pages[page_no - 1])

        methods = [(f"camelot-{f}", lambda f=f: run_camelot(pdf_path, page_no, f)) for f in CAMELOT_FLAVORS]
        methods.append(("pdfplumber-text", lambda: run_pdfplumber_text(pdf_path, page_no)))

        for name, fn in methods:
            rec = {"stem": stem, "page": page_no, "kind": kind, "method": name,
                   "h_rulings": h, "v_rulings": v}
            t0 = time.perf_counter()
            try:
                tables = fn()
                rec["n_tables"] = len(tables)
                for k, (df, _, _) in enumerate(tables, start=1):
                    df.to_csv(out / f"{stem}_p{page_no:04d}_{name}_t{k}.csv", index=False, header=False)
                if tables:
                    df, acc, ws = max(tables, key=lambda t: t[0].size)
                    rec.update(status="ok", largest_shape=f"{df.shape[0]}x{df.shape[1]}",
                               accuracy=acc, whitespace=ws)
                else:
                    rec["status"] = "no_tables"
            except Exception as e:  # a failing method is a bake-off result, not a crash
                rec.update(status="error", error=f"{type(e).__name__}: {e}"[:200])
            rec["seconds"] = round(time.perf_counter() - t0, 3)
            rows.append(rec)
            print(f"{stem} p{page_no:<2} {kind:<7} {name:<16} {rec['status']:<9} "
                  f"tables={rec.get('n_tables', '-')} shape={rec.get('largest_shape', '-')} "
                  f"acc={rec.get('accuracy', '-')} {rec['seconds']}s {rec.get('error', '')}")

    with open(out / "summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out / 'summary.csv'} ({len(rows)} rows); rulings per page in h_rulings/v_rulings")


if __name__ == "__main__":
    main()
