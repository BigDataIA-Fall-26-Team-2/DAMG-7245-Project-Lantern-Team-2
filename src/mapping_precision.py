"""Automated label mapping without the dictionary (stretch, #82).

Runs `xbrl.py compare` with an empty label map (same structure as config/label_map.yaml, no
entries), so only the automatic layers map labels: Apple's label linkbase, then fuzzy matching
(cutoff in params.yaml). Scores the result against the verified comparison in data/xbrl, whose
388 cells per path are all confirmed by value (match, or sign proven by negatedLabel).

    python src/mapping_precision.py --reference data/xbrl --output reports/mapping_precision.csv
"""
import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

KEY = ["stem", "statement", "page", "pdf_label", "period_label"]
PATHS = {"traditional": "data/tables", "docling": "data/docling/tables"}


def empty_label_map(label_map, out):
    """The dictionary's skeleton with every statement's list emptied: no dictionary entries."""
    raw = yaml.safe_load(Path(label_map).read_text())
    Path(out).write_text(yaml.safe_dump({"version": raw.get("version", 1),
                                         "lines": {st: [] for st in raw["lines"]}}))


def scores(ref, auto):
    """Coverage and precision of auto against ref, matched per cell; empty dims count as equal."""
    m = ref.merge(auto, on=KEY, how="left", suffixes=("_ref", "_auto"))
    for c in ("prefix", "concept", "dims"):
        for s in ("_ref", "_auto"):
            m[c + s] = m[c + s].fillna("").astype(str)
    mapped = m.concept_auto != ""
    right = mapped & (m.prefix_ref == m.prefix_auto) & (m.concept_ref == m.concept_auto) & (m.dims_ref == m.dims_auto)
    short = m.pdf_label.str.rsplit(": ", n=1).str[-1]
    return {"cells": len(m), "mapped": int(mapped.sum()), "coverage": round(mapped.mean(), 4),
            "right": int(right.sum()), "precision": round(right.sum() / max(mapped.sum(), 1), 4),
            "wrong_labels": "; ".join(sorted(short[mapped & ~right].unique())),
            "unmapped_labels": "; ".join(sorted(short[~mapped].str[:60].unique()))}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mapping precision without the label dictionary (#82)")
    ap.add_argument("--reference", default="data/xbrl", help="folder with the verified comparison_{path}.csv")
    ap.add_argument("--label-map", default="config/label_map.yaml")
    ap.add_argument("--work", default="data/automap", help="folder for the no-dictionary comparison")
    ap.add_argument("--output", default="reports/mapping_precision.csv")
    a = ap.parse_args(argv)
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    empty = work / "empty_label_map.yaml"
    empty_label_map(a.label_map, empty)
    rows = []
    for path, tables in PATHS.items():
        subprocess.run([sys.executable, "src/xbrl.py", "compare", "--path", path, "--tables", tables,
                        "--label-map", str(empty), "--output", str(work)], check=True,
                       stdout=subprocess.DEVNULL)
        ref = pd.read_csv(Path(a.reference) / f"comparison_{path}.csv")
        auto = pd.read_csv(work / f"comparison_{path}.csv")
        rows.append({"path": path, **scores(ref, auto)})
    out = pd.DataFrame(rows)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.output, index=False)
    for r in rows:
        print(f"{r['path']}: coverage {r['coverage']:.1%} ({r['mapped']}/{r['cells']}), "
              f"precision {r['precision']:.1%} ({r['right']}/{r['mapped']})")
    print(f"wrote {a.output}")


if __name__ == "__main__":
    main()
