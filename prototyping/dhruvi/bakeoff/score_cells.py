"""Score Part 2 bake-off methods against hand-transcribed cells (gt_cells.csv).

For each page and method: find the row whose label matches the ground-truth label
(n-th occurrence), take the period_index-th number in that row, compare as exact text.
Writes cell_check.csv (one row per cell x method) and cell_scores.csv (summary).
"""
import argparse
import re
from pathlib import Path

import pandas as pd

METHODS = ["camelot-lattice", "camelot-stream", "camelot-network", "camelot-hybrid", "pdfplumber-text"]
NUMBER = re.compile(r"^\(?-?\d[\d,]*(\.\d+)?\)?$")


def norm_label(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_row(row):
    """Split a table row into (normalized label, [number tokens]); '$' tokens are ignored."""
    label_tokens, numbers = [], []
    for cell in row:
        for token in str(cell).split():
            token = token.replace("$", "")
            if not token:
                continue
            (numbers if NUMBER.match(token) else label_tokens).append(token)
    return norm_label(" ".join(label_tokens)), numbers


def method_rows(results, stem, page, method):
    rows = []
    for f in sorted(results.glob(f"{stem}_p{page:04d}_{method}_t*.csv")):
        rows += pd.read_csv(f, header=None, dtype=str, keep_default_na=False).values.tolist()
    return [parse_row(r) for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", default="prototyping/dhruvi/bakeoff/gt_cells.csv")
    ap.add_argument("--input", default="prototyping/dhruvi/bakeoff/results", help="bake-off CSV folder")
    ap.add_argument("--output", default="prototyping/dhruvi/bakeoff/results")
    args = ap.parse_args()
    results, out = Path(args.input), Path(args.output)

    gt = pd.read_csv(args.gt, dtype=str, keep_default_na=False)
    detail = []
    for (stem, page), cells in gt.groupby(["stem", "page"], sort=False):
        page = int(page)
        for method in METHODS:
            parsed = method_rows(results, stem, page, method)
            every_number = {n for _, nums in parsed for n in nums}
            for _, c in cells.iterrows():
                want = c["value"].replace(" ", "")
                hits = [nums for label, nums in parsed if label == norm_label(c["label"])]
                occ, idx = int(c["occurrence"]), int(c["period_index"])
                got = hits[occ - 1][idx] if len(hits) >= occ and len(hits[occ - 1]) > idx else ""
                detail.append({"stem": stem, "page": page, "method": method, "label": c["label"],
                               "period": c["period"], "expected": want, "extracted": got,
                               "correct": got == want, "label_found": len(hits) >= occ,
                               "value_anywhere": want in every_number})

    det = pd.DataFrame(detail)
    det.to_csv(out / "cell_check.csv", index=False)
    scores = (det.groupby(["stem", "page", "method"], sort=False)
                 .agg(cells=("correct", "size"), correct=("correct", "sum"),
                      label_found=("label_found", "sum"), value_anywhere=("value_anywhere", "sum"))
                 .reset_index())
    scores["cell_accuracy"] = (scores["correct"] / scores["cells"]).round(2)
    scores.to_csv(out / "cell_scores.csv", index=False)
    print(scores.to_string(index=False))
    overall = det.groupby("method", sort=False)[["correct", "label_found", "value_anywhere"]].sum()
    overall["of"] = det.groupby("method", sort=False).size()
    print("\n===== overall (40 cells per method) =====")
    print(overall.to_string())


if __name__ == "__main__":
    main()
