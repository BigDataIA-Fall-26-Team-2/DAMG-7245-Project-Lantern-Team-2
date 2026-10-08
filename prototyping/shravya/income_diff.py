"""P4 Exercise 4.1: Docling vs traditional (P2) statement tables, cell by cell, on the four statement pages."""
import pandas as pd

PAGES = [("AAPL_10K_20250927", 32, "income"), ("AAPL_10K_20250927", 34, "balance"),
         ("AAPL_10Q_20260627", 4, "income"), ("AAPL_10Q_20260627", 6, "balance")]

def load(path):
    d = pd.read_csv(path)
    d["n"] = d.groupby(["row_label", "col_label"]).cumcount()   # tell repeated labels apart (Products #0, #1)
    return d.set_index(["row_label", "col_label", "n"])

for stem, page, kind in PAGES:
    name = f"{stem}_p{page:04d}_t1.csv"
    try:
        trad, dl = load(f"data/tables/{name}"), load(f"data/docling/tables/{name}")
    except FileNotFoundError as e:
        print(f"{stem} p{page} {kind}: missing file ({e.filename})")
        continue
    both = trad.join(dl, how="outer", lsuffix="_trad", rsuffix="_dl")
    matched = both.dropna(subset=["value_trad", "value_dl"])
    diff = matched[matched["value_trad"] != matched["value_dl"]]
    only_trad, only_dl = both["value_dl"].isna().sum(), both["value_trad"].isna().sum()
    print(f"{stem} p{page} {kind}: trad {len(trad)}, docling {len(dl)}, matched {len(matched)}, "
          f"same {len(matched) - len(diff)}, different {len(diff)}, only trad {only_trad}, only docling {only_dl}")
    if len(diff):
        print(diff[["raw_trad", "value_trad", "raw_dl", "value_dl"]].head(5).to_string())
