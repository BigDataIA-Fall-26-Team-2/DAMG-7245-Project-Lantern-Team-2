"""Measure storage formats for one document (Part 6, issue #58).

For each FORMAT=PATH it records bytes, characters, approximate tokens (characters / 4, as the
brief allows) and what page provenance the format carries, measured from the file itself:
  - jsonl: records with a `page` and a `bbox`
  - json:  Docling provenance entries (`"page_no"`)
  - md:    provenance comments (`<!-- ... -->`)
  - txt:   form-feed page breaks (page number only, no position)

Run:
  python src/format_stats.py --output reports/format_stats.csv \\
      md=data/docling/AAPL_10K_20250927.md jsonl=data/export/AAPL_10K_20250927.docling.jsonl \\
      json=data/docling/AAPL_10K_20250927.json txt=data/export/AAPL_10K_20250927.txt
"""
import argparse
import csv
import json
from pathlib import Path


def provenance(fmt, text):
    if fmt == "jsonl":
        recs = [json.loads(line) for line in text.splitlines() if line.strip()]
        with_box = sum(1 for r in recs if r.get("page") is not None and r.get("bbox"))
        return len(recs), f"{with_box}/{len(recs)} records with page + bbox"
    if fmt == "json":
        return None, f'{text.count(chr(34) + "page_no" + chr(34))} page_no entries (page + bbox per item)'
    if fmt == "md":
        return None, f"{text.count('<!--')} provenance comments"
    if fmt == "txt":
        return None, f"{text.count(chr(12)) + 1} pages separated by form feeds, no positions"
    return None, ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Size, tokens and provenance per storage format")
    ap.add_argument("files", nargs="+", help="FORMAT=PATH, FORMAT in md, jsonl, json, txt")
    ap.add_argument("--output", default="reports/format_stats.csv")
    a = ap.parse_args(argv)
    rows = []
    for item in a.files:
        fmt, path = item.split("=", 1)
        text = Path(path).read_text(encoding="utf-8")
        records, prov = provenance(fmt, text)
        rows.append({"format": fmt, "path": path, "bytes": Path(path).stat().st_size,
                     "chars": len(text), "approx_tokens": len(text) // 4,
                     "records": records if records is not None else "", "page_provenance": prov})
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['format']:<6} {r['bytes']:>10,} B {r['chars']:>10,} chars ~{r['approx_tokens']:>9,} tokens"
              f"  {r['page_provenance']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
