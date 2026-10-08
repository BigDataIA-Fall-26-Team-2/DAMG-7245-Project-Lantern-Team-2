"""Part 9: accuracy and drift measurement against hand-made ground truth.

Reads data/ground_truth/*.gt.txt and *.gt.csv, compares against the export
stage output, and writes reports/metrics.json plus reports/plots/drift.png.

Normalisation is applied identically to reference and hypothesis, exactly as
declared in data/ground_truth/CONVENTIONS.md. Applying a substitution to one
side only would manufacture a difference the transcriber chose rather than one
the parser made.

--break <mode> deliberately degrades the hypothesis before scoring. It exists
to show that these metrics detect a regression rather than merely producing a
comfortable number. See reports/eval.md.
"""

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import jiwer
import yaml

_SUBS = [
    ("\u00ae", ""),      # registered trademark, omitted in transcription
    ("\u2122", ""),      # trademark, omitted in transcription
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u2014", "-"),     # em dash
    ("\u2013", "-"),     # en dash
    ("\u2212", "-"),     # minus sign
    ("\u2612", "[X]"),   # ballot box with X
    ("\u2611", "[X]"),
    ("\u2610", "[ ]"),
    ("\u00a0", " "),
]

_TRANSFORM = jiwer.Compose([
    jiwer.ToLowerCase(),
    jiwer.RemoveMultipleSpaces(),
    jiwer.Strip(),
])

_NUM_RE = re.compile(r"\(?-?\$?\d[\d,]*(?:\.\d+)?\)?%?")

PATHS = ("traditional", "docling", "managed")

BREAK_MODES = ("none", "no-scale", "drop-parens", "no-ocr", "strip-prefix")


def apply_conventions(s):
    s = unicodedata.normalize("NFKC", s)
    for a, b in _SUBS:
        s = s.replace(a, b)
    return s


def normalise(s):
    """Conventions substitutions, then lower-case and whitespace collapse.

    Punctuation is deliberately NOT removed: removing it turns (1,234) into
    1234 and hides a sign error, the one error class a financial pipeline
    cannot afford to hide.
    """
    s = apply_conventions(s)
    s = re.sub(r"\s+", " ", s)
    return _TRANSFORM(s)


def numeric_tokens(s):
    return _NUM_RE.findall(apply_conventions(s))


def to_number(raw):
    if raw is None:
        return None
    s = apply_conventions(str(raw))
    s = s.replace("$", "").replace(",", "").replace("%", "").strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


# --- metric primitives ----------------------------------------------------

def prf(ref_set, hyp_set):
    tp = len(ref_set & hyp_set)
    p = tp / len(hyp_set) if hyp_set else 0.0
    r = tp / len(ref_set) if ref_set else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
            "tp": tp, "ref_n": len(ref_set), "hyp_n": len(hyp_set)}


def text_metrics(ref, hyp):
    r, h = normalise(ref), normalise(hyp)
    if not r:
        return None
    out = {
        "wer": round(jiwer.wer(r, h), 4),
        "cer": round(jiwer.cer(r, h), 4),
        "ref_words": len(r.split()),
        "hyp_words": len(h.split()),
    }
    rn, hn = numeric_tokens(ref), numeric_tokens(hyp)
    out["numeric"] = prf(set(rn), set(hn))
    out["numeric"]["ref_tokens"] = len(rn)
    out["numeric"]["hyp_tokens"] = len(hn)
    return out


# --- loading --------------------------------------------------------------

def load_export(path, break_mode="none"):
    by_page = defaultdict(list)
    if not path.exists():
        return by_page
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rec = degrade(rec, break_mode)
            if rec is not None:
                by_page[rec["page"]].append(rec)
    return by_page


def degrade(rec, mode):
    """Deliberately break one behaviour, to show the metrics have teeth."""
    if mode == "none":
        return rec
    if mode == "no-ocr":
        # simulate OCR never running: drop blocks that only exist via OCR
        return None if rec.get("ocr") else rec
    t = rec.get("table")
    if mode == "no-scale" and t and t.get("rows"):
        # simulate forgetting the per-row scale: carry the printed figure
        # through as if it were already in full units
        raws = t.get("raw_cells") or t["rows"]
        new_rows = []
        for ri, row in enumerate(t["rows"]):
            raw_row = raws[ri] if ri < len(raws) else row
            out = [row[0]]
            for ci in range(1, len(row)):
                src = raw_row[ci] if ci < len(raw_row) else row[ci]
                out.append(str(src).replace(",", "").replace("$", "").strip())
            new_rows.append(out)
        t["rows"] = new_rows
    if mode == "drop-parens":
        if rec.get("text"):
            rec["text"] = rec["text"].replace("(", "").replace(")", "")
        if t:
            for key in ("rows", "raw_cells"):
                if t.get(key):
                    t[key] = [[str(c).replace("(", "").replace(")", "")
                               if c is not None else c for c in row]
                              for row in t[key]]
    if mode == "strip-prefix" and t:
        for key in ("rows", "raw_cells"):
            if t.get(key):
                t[key] = [[(str(row[0]).split(": ")[-1] if i == 0 else c)
                           for i, c in enumerate(row)] for row in t[key]]
    return rec


def table_as_text(rec):
    """Table record -> tab separated rows, matching the reference convention.

    CONVENTIONS.md records a table as one line per row with cells separated by
    a single tab, so the hypothesis must be built the same way. raw_cells is
    used rather than rows, because the reference records what is printed, not
    the scaled value.
    """
    t = rec.get("table") or {}
    grid = t.get("raw_cells") or t.get("rows") or []
    return "\n".join("\t".join("" if c is None else str(c) for c in row)
                     for row in grid)


def page_text(records):
    parts = []
    for r in records:
        if r.get("text"):
            parts.append((r["bbox"][1], r["bbox"][0], r["text"]))
        elif r.get("block_type") == "Table" and r.get("table"):
            s = table_as_text(r)
            if s:
                parts.append((r["bbox"][1], r["bbox"][0], s))
    parts.sort(key=lambda p: (p[0], p[1]))
    return "\n".join(p[2] for p in parts)


def gt_section_headings(rows):
    """Normalised labels of bare section-heading rows in a ground-truth table.

    A heading is a row whose label ends in a colon and whose cells hold no
    value, for example "Net sales:". Used to strip a section prefix from row
    labels on both sides at scoring time.
    """
    by_label = {}
    for r in rows:
        lab = normalise(r["row_label"])
        has_value = to_number(r.get("value") or r.get("raw")) is not None
        by_label[lab] = by_label.get(lab, False) or has_value
    return {lab for lab, has_value in by_label.items()
            if lab.endswith(":") and not has_value}


def strip_section(label, headings):
    """Remove a known section prefix, so prefix scope is not scored.

    Two transcribers, the traditional parser and Textract apply the section
    prefix differently: to every row in a section, only to labels that repeat,
    or not at all. That is a representation choice, not a reading error, so it
    is neutralised on both sides the same way the conventions neutralise em
    dashes and quotes. Only a prefix equal to one of the table's own heading
    rows is removed, so a colon that is part of a label (for example "par
    value: 50,400,000 shares") is left alone. Repeated labels such as
    "Products" are still told apart, by their value.
    """
    for h in sorted(headings, key=len, reverse=True):
        if label.startswith(h + " "):
            return label[len(h) + 1:]
    return label


def load_gt_table(path):
    """gt csv -> cells keyed for scoring.

    Returns a dict with:
      cells      {(label, col, scaled value)}  scale applied, as in "value"
      cells_raw  {(label, col, printed figure)} unscaled, from "raw"
      values     {scaled value}
      cols       column labels in order
      headings   section-heading labels, for prefix stripping
    """
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
    cols = []
    for r in rows:
        if r["col_label"] not in cols:
            cols.append(r["col_label"])
    headings = gt_section_headings(rows)
    cells, cells_raw, values = set(), set(), set()
    for r in rows:
        label = strip_section(normalise(r["row_label"]), headings)
        ci = cols.index(r["col_label"])
        v = to_number(r.get("value") or r.get("raw"))
        if v is not None:
            cells.add((label, ci, v))
            values.add(v)
        raw_v = to_number(r.get("raw"))
        if raw_v is not None:
            cells_raw.add((label, ci, raw_v))
    return {"cells": cells, "cells_raw": cells_raw, "values": values,
            "cols": cols, "headings": headings}


def table_records(records):
    return [r for r in records
            if r.get("block_type") == "Table" and r.get("table")]


def parser_table_cells(rec, headings=frozenset()):
    """Export Table record -> (cells, cells_raw, values).

    Column index is positional, because extractors do not reliably recover
    real column headers: on 10-K page 22 Camelot's came back as col1, col2,
    col3. Keying on the header string would score every cell zero on those
    tables even where the figure was read correctly.

    cells uses the scaled "rows"; cells_raw uses the printed "raw_cells"
    unscaled, so that a path which does not normalise scale (Textract) is
    scored on reading rather than on a normalisation step it never attempts.
    """
    t = rec["table"]
    rows = t.get("rows") or []
    raws = t.get("raw_cells") or rows
    cells, cells_raw, values = set(), set(), set()
    for ri, row in enumerate(rows):
        if not row:
            continue
        label = strip_section(normalise(str(row[0] or "")), headings)
        raw_row = raws[ri] if ri < len(raws) else row
        for ci in range(1, len(row)):
            v = to_number(row[ci])
            if v is None and ci < len(raw_row):
                v = to_number(raw_row[ci])
            if v is not None:
                cells.add((label, ci - 1, v))
                values.add(v)
            if ci < len(raw_row):
                rv = to_number(raw_row[ci])
                if rv is not None:
                    cells_raw.add((label, ci - 1, rv))
    return cells, cells_raw, values


# --- drift ----------------------------------------------------------------

def block_lengths(by_page):
    out = []
    for recs in by_page.values():
        for r in recs:
            if r.get("text"):
                out.append(len(r["text"]))
    return out


def write_plot(results, exports, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))

    ax = axes[0]
    for name, style in (("traditional", "-"), ("docling", "--")):
        lens = []
        for paths in exports.values():
            lens += block_lengths(paths[name])
        if lens:
            ax.hist(lens, bins=40, range=(0, 2000), histtype="step",
                    linestyle=style, label=f"{name} (n={len(lens)})")
    ax.set_xlabel("text block length (characters)")
    ax.set_ylabel("blocks")
    ax.set_title("Chunk length distribution")
    ax.legend(fontsize=8)

    ax = axes[1]
    strata = sorted({v["stratum"] for v in results["pages"].values()})
    width = 0.38
    for i, name in enumerate(("traditional", "docling")):
        vals = [results["by_stratum"].get(name, {}).get(s, {}).get("wer_mean", 0)
                for s in strata]
        ax.bar([x + i * width for x in range(len(strata))], vals, width,
               label=name)
    ax.set_xticks([x + width / 2 for x in range(len(strata))])
    ax.set_xticklabels(strata, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("mean WER")
    ax.set_title("WER by stratum")
    ax.legend(fontsize=8)

    ax = axes[2]
    for i, name in enumerate(("traditional", "docling")):
        vals = [results["by_stratum"].get(name, {}).get(s, {})
                .get("numeric_f1_mean", 0) for s in strata]
        ax.bar([x + i * width for x in range(len(strata))], vals, width,
               label=name)
    ax.set_xticks([x + width / 2 for x in range(len(strata))])
    ax.set_xticklabels(strata, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("mean numeric token F1")
    ax.set_title("Numeric token F1 by stratum")
    ax.legend(fontsize=8)

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


# --- main -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default="params.yaml")
    ap.add_argument("--break", dest="break_mode", default="none",
                    choices=BREAK_MODES,
                    help="deliberately degrade the hypothesis, to show the "
                         "metrics detect a regression")
    ap.add_argument("--out", default=None,
                    help="override metrics output path")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.params, encoding="utf-8"))["evaluate"]
    gt_dir = Path(cfg["gt_dir"])
    export_dir = Path(cfg["export_dir"])
    out_path = Path(args.out or cfg["metrics_out"])
    strata = cfg["strata"]

    results = {"break_mode": args.break_mode, "pages": {}, "tables": {},
               "by_stratum": {}, "by_path": {}}

    managed_cfg = (yaml.safe_load(open(args.params, encoding="utf-8"))
                   .get("managed", {}) or {})
    managed_dir = Path(managed_cfg.get("cache_dir", "data/managed"))
    fixture_stems = list((managed_cfg.get("fixture_pages") or {}).keys())

    exports = {}
    for stem in list(cfg["stems"]) + fixture_stems:
        exports[stem] = {
            "traditional": load_export(export_dir / f"{stem}.jsonl",
                                       args.break_mode),
            "docling": load_export(export_dir / f"{stem}.docling.jsonl",
                                   args.break_mode),
            # Part 7: AWS Textract via src/managed/textract.py. Read from the
            # cache only; evaluation never calls the service.
            "managed": load_export(managed_dir / f"{stem}.blocks.jsonl",
                                   args.break_mode),
        }

    for key, stratum in strata.items():
        gt_file = gt_dir / f"{key}.gt.txt"
        if not gt_file.exists():
            continue
        ref = gt_file.read_text(encoding="utf-8")
        stem, _, page_s = key.rpartition("_p")
        try:
            page = int(page_s)
        except ValueError:
            continue
        entry = {"stratum": stratum, "page": page}
        for path_name in PATHS:
            by_page = exports.get(stem, {}).get(path_name)
            if not by_page or page not in by_page:
                continue
            m = text_metrics(ref, page_text(by_page[page]))
            if m:
                entry[path_name] = m
        results["pages"][key] = entry

    for gt_file in sorted(gt_dir.glob("*_t*.gt.csv")):
        key = gt_file.name[: -len(".gt.csv")]
        base, _, _ = key.rpartition("_t")
        stem, _, page_s = base.rpartition("_p")
        page = int(page_s)
        gt = load_gt_table(gt_file)
        entry = {"page": page, "gt_columns": gt["cols"]}
        for path_name in ("traditional", "managed"):
            by_page = exports.get(stem, {}).get(path_name, {})
            found = table_records(by_page.get(page, []))
            if not found:
                continue
            hc, hcr, hv = set(), set(), set()
            for rec in found:
                c, cr, v = parser_table_cells(rec, gt["headings"])
                hc |= c
                hcr |= cr
                hv |= v
            res = {
                "tables_found": len(found),
                "columns": [r["table"].get("columns") for r in found],
                "extractor": sorted({r.get("extractor") for r in found}),
                # printed figures, unscaled: measures reading, comparable
                # across every path
                "cell_raw": prf(gt["cells_raw"], hcr),
            }
            if path_name == "traditional":
                # scale applied: also tests Part 2's normalisation. Textract
                # does no scale normalisation, so it is not scored on this.
                res["cell"] = prf(gt["cells"], hc)
                res["value"] = prf(gt["values"], hv)
            entry[path_name] = res
        # keep the old top-level keys so the quality gates still read them
        if "traditional" in entry:
            entry["cell"] = entry["traditional"]["cell"]
            entry["value"] = entry["traditional"]["value"]
        results["tables"][key] = entry

    for path_name in PATHS:
        buckets = defaultdict(list)
        for entry in results["pages"].values():
            if path_name in entry:
                buckets[entry["stratum"]].append(entry[path_name])
        per_stratum = {}
        for stratum, ms in buckets.items():
            per_stratum[stratum] = {
                "n_pages": len(ms),
                "wer_mean": round(sum(m["wer"] for m in ms) / len(ms), 4),
                "wer_max": round(max(m["wer"] for m in ms), 4),
                "cer_mean": round(sum(m["cer"] for m in ms) / len(ms), 4),
                "numeric_f1_mean": round(
                    sum(m["numeric"]["f1"] for m in ms) / len(ms), 4),
                "numeric_f1_min": round(
                    min(m["numeric"]["f1"] for m in ms), 4),
            }
        results["by_stratum"][path_name] = per_stratum
        allm = [m for ms in buckets.values() for m in ms]
        if allm:
            results["by_path"][path_name] = {
                "n_pages": len(allm),
                "wer_mean": round(sum(m["wer"] for m in allm) / len(allm), 4),
                "cer_mean": round(sum(m["cer"] for m in allm) / len(allm), 4),
                "numeric_f1_mean": round(
                    sum(m["numeric"]["f1"] for m in allm) / len(allm), 4),
            }

    # Part 7 side-by-side: only pages the managed path covers, so the three
    # paths are compared on identical inputs rather than on different samples
    side = {}
    for key, entry in results["pages"].items():
        if "managed" not in entry:
            continue
        side[key] = {"stratum": entry["stratum"]}
        for path_name in PATHS:
            m = entry.get(path_name)
            if m:
                side[key][path_name] = {
                    "wer": m["wer"], "cer": m["cer"],
                    "numeric_f1": m["numeric"]["f1"],
                }
    for key, t in results["tables"].items():
        if "managed" in t:
            side[key] = {
                p: {"cell_raw_f1": t[p]["cell_raw"]["f1"],
                    "tables_found": t[p]["tables_found"]}
                for p in ("traditional", "managed") if p in t
            }
    results["side_by_side"] = side

    ocr_pages = {}
    for stem, paths in exports.items():
        by_page = paths["traditional"]
        total = len(by_page)
        if not total:
            continue
        ocr = sum(1 for recs in by_page.values() if any(r.get("ocr") for r in recs))
        ocr_pages[stem] = {
            "pages": total,
            "ocr_pages": ocr,
            "ocr_share": round(ocr / total, 4) if total else 0.0,
        }
    lens = []
    for paths in exports.values():
        lens += block_lengths(paths["traditional"])
    results["drift"] = {
        "ocr": ocr_pages,
        "chunk_chars_mean": round(sum(lens) / len(lens), 1) if lens else 0.0,
        "chunk_chars_n": len(lens),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    if not args.no_plot and args.break_mode == "none":
        write_plot(results, exports, Path(cfg.get(
            "plot_out", "reports/plots/drift.png")))

    print(json.dumps({"break_mode": args.break_mode,
                      "by_path": results["by_path"]}, indent=2))
    print(json.dumps({k: v.get("cell", {}).get("f1")
                      for k, v in results["tables"].items()}, indent=2))
    print(json.dumps(results["by_stratum"]["traditional"], indent=2))
    print(json.dumps(results["side_by_side"], indent=2))


if __name__ == "__main__":
    main()