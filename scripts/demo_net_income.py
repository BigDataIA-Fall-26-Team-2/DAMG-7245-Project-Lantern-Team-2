"""Demo (#70): one number end to end.

Net income for fiscal 2025 in the 10-K, traced through every stage:
iXBRL filing -> rendered PDF page (box drawn) -> JSONL record -> Markdown line
with provenance -> Arelle fact -> XBRL match status.

Run from the repo root after the pipeline has run:
    python scripts/demo_net_income.py
Writes reports/demo_net_income_p32.png.
"""

import csv
import json
import re
from pathlib import Path

import pdfplumber

STEM = "AAPL_10K_20250927"
PAGE = 32
RAW = "112,010"
CONCEPT = "NetIncomeLoss"
PERIOD = "FY ended 2025-09-27"
LABEL = "net income"
IMAGE = Path("reports/demo_net_income_p32.png")


def manifest_row():
    with open("data/rendered/manifest.csv", newline="", encoding="utf-8") as f:
        return next(r for r in csv.DictReader(f) if r["stem"] == STEM)


def step1_ixbrl(row):
    path = Path(row["source_file"].replace("\\", "/"))
    doc = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<ix:nonFraction\b([^>]*\bname=\"us-gaap:" + CONCEPT +
                  r"\"[^>]*)>\s*" + re.escape(RAW) + r"\s*</ix:nonFraction>", doc)
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    ctx = re.search(r'<xbrli:context id="' + re.escape(attrs["contextRef"]) +
                    r'">(.*?)</xbrli:context>', doc, re.DOTALL).group(1)
    start = re.search(r"<xbrli:startDate>(.*?)</xbrli:startDate>", ctx).group(1)
    end = re.search(r"<xbrli:endDate>(.*?)</xbrli:endDate>", ctx).group(1)
    print("1  EDGAR iXBRL")
    print(f"   file        {path}")
    print(f"   element     ix:nonFraction name=us-gaap:{CONCEPT}")
    print(f"   printed     {RAW}")
    print(f"   scale       {attrs.get('scale')}   decimals {attrs.get('decimals')}"
          f"   unit {attrs.get('unitRef')}")
    print(f"   context     {attrs['contextRef']}   {start} to {end}")


def find_record():
    for line in open(f"data/export/{STEM}.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["page"] != PAGE or r["block_type"] != "Table":
            continue
        for i, row in enumerate(r["table"]["rows"]):
            if str(row[0]).strip().lower() == LABEL:
                return r, i
    raise SystemExit(f"no Table record on page {PAGE} with a '{LABEL}' row")


def step2_page(rec):
    pdf_path = Path(rec["source_path"])
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[PAGE - 1]
        words = page.extract_words()
        hit = next(w for w in words if w["text"] == RAW and any(
            abs(o["top"] - w["top"]) < 3 and o["text"].lower() == "income"
            for o in words))
        line = [w for w in words if abs(w["top"] - hit["top"]) < 3]
        row_box = (min(w["x0"] for w in line), min(w["top"] for w in line),
                   max(w["x1"] for w in line), max(w["bottom"] for w in line))
        im = page.to_image(resolution=150)
        im.draw_rect(tuple(rec["bbox"]), stroke=(30, 90, 220), fill=(30, 90, 220, 25),
                     stroke_width=3)
        im.draw_rect(row_box, stroke=(220, 30, 30), fill=(220, 30, 30, 50),
                     stroke_width=3)
        IMAGE.parent.mkdir(parents=True, exist_ok=True)
        im.save(IMAGE)
    print("2  Rendered PDF")
    print(f"   file        {pdf_path}   page {PAGE}")
    print(f"   row text    {' '.join(w['text'] for w in line)}")
    print(f"   row bbox    {[round(c, 1) for c in row_box]}   (red)")
    print(f"   record bbox {rec['bbox']}   (blue)")
    print(f"   image       {IMAGE}")


def step3_jsonl(rec, i):
    t = rec["table"]
    print("3  JSONL record")
    for key in ("doc_id", "fiscal_year", "fiscal_period", "page", "section",
                "block_id", "block_type", "bbox", "extractor", "extractor_version",
                "source_path"):
        print(f"   {key:<18}{rec[key]}")
    print(f"   {'sha256':<18}{rec['sha256'][:16]}...")
    print(f"   {'columns':<18}{t['columns']}")
    print(f"   {'raw_cells':<18}{t['raw_cells'][i]}")
    print(f"   {'rows':<18}{t['rows'][i]}")
    print(f"   {'scale':<18}{t['scale']}")


def step4_markdown(rec):
    lines = Path(f"data/export/{STEM}.md").read_text(encoding="utf-8").splitlines()
    start = next(k for k, l in enumerate(lines)
                 if l.startswith("<!--") and f'"block_id": "{rec["block_id"]}"' in l
                 and f'"page": {PAGE}' in l)
    row = next(l for l in lines[start:] if l.lower().startswith(f"| {LABEL} |"))
    print("4  Markdown with provenance")
    print(f"   {lines[start]}")
    print(f"   {row}")


def step5_xbrl():
    with open("data/xbrl/facts.csv", newline="", encoding="utf-8") as f:
        fact = next(r for r in csv.DictReader(f)
                    if r["stem"] == STEM and r["concept"] == CONCEPT
                    and r["period_label"] == PERIOD and r["n_dims"] == "0")
    print("5  Arelle fact")
    print(f"   concept     {fact['prefix']}:{fact['concept']}   ({fact['label']})")
    print(f"   value       {fact['value']} {fact['unit']}   decimals {fact['decimals']}")
    print(f"   period      {fact['start']} to {fact['end']}   ({fact['months']} months)")


def step6_match():
    print("6  XBRL match status")
    for path in ("traditional", "docling"):
        with open(f"data/xbrl/comparison_{path}.csv", newline="", encoding="utf-8") as f:
            c = next(r for r in csv.DictReader(f)
                     if r["stem"] == STEM and r["concept"] == CONCEPT
                     and r["statement"] == "income" and r["period_label"] == PERIOD)
        print(f"   {path:<12}pdf {c['pdf_raw']} -> {c['pdf_value']}   "
              f"xbrl {c['xbrl_value']}   tolerance {c['tolerance']}   "
              f"status {c['status']}   mapping {c['mapping']}")


def main():
    row = manifest_row()
    rec, i = find_record()
    step1_ixbrl(row)
    step2_page(rec)
    step3_jsonl(rec, i)
    step4_markdown(rec)
    step5_xbrl()
    step6_match()


if __name__ == "__main__":
    main()