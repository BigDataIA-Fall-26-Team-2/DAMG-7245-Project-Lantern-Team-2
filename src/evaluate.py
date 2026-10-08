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


def load_gt_table(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
    cols = []
    for r in rows:
        if r["col_label"] not in cols:
            cols.append(r["col_label"])
    cells, values = set(), set()
    for r in rows:
        v = to_number(r.get("value") or r.get("raw"))
        if v is None:
            continue
        cells.add((normalise(r["row_label"]), cols.index(r["col_label"]), v))
        values.add(v)
    return cells, values, cols


def table_records(records):
    return [r for r in records
            if r.get("block_type") == "Table" and r.get("table")]


def parser_table_cells(rec):
    """Export Table record -> (cells, values).

    Column index is positional, because the extractor does not reliably
    recover real column headers: on 10-K page 22 the columns came back as
    col1, col2, col3. Keying on the header string would score every cell zero
    on those tables even where the figure was read correctly.
    """
    t = rec["table"]
    rows = t.get("rows") or []
    raws = t.get("raw_cells") or rows
    cells, values = set(), set()
    for ri, row in enumerate(rows):
        if not row:
            continue
        label = normalise(str(row[0] or ""))
        raw_row = raws[ri] if ri < len(raws) else row
        for ci in range(1, len(row)):
            v = to_number(row[ci])
            if v is None and ci < len(raw_row):
                v = to_number(raw_row[ci])
            if v is None:
                continue
            cells.add((label, ci - 1, v))
            values.add(v)
    return cells, values


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

    exports = {}
    for stem in cfg["stems"]:
        exports[stem] = {
            "traditional": load_export(export_dir / f"{stem}.jsonl",
                                       args.break_mode),
            "docling": load_export(export_dir / f"{stem}.docling.jsonl",
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
        for path_name in ("traditional", "docling"):
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
        ref_cells, ref_values, cols = load_gt_table(gt_file)
        by_page = exports.get(stem, {}).get("traditional", {})
        found = table_records(by_page.get(page, []))
        hyp_cells, hyp_values = set(), set()
        for rec in found:
            c, v = parser_table_cells(rec)
            hyp_cells |= c
            hyp_values |= v
        results["tables"][key] = {
            "page": page,
            "gt_columns": cols,
            "cell": prf(ref_cells, hyp_cells),
            "value": prf(ref_values, hyp_values),
            "parser_tables_found": len(found),
            "parser_columns": [r["table"].get("columns") for r in found],
        }

    for path_name in ("traditional", "docling"):
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

    ocr_pages = {}
    for stem, paths in exports.items():
        by_page = paths["traditional"]
        total = len(by_page)
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
    print(json.dumps({k: v["cell"]["f1"] for k, v in results["tables"].items()},
                     indent=2))
    print(json.dumps(results["by_stratum"]["traditional"], indent=2))


if __name__ == "__main__":
    main()