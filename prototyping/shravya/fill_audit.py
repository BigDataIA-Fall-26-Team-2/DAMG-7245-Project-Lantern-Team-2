"""Fill layout_audit.csv with the manual audit counts (judged from reports/layout/ overlays)."""
import csv
from pathlib import Path

K, Q = "AAPL_10K_20250927", "AAPL_10Q_20260627"
# (stem, page, class): (correct, missed, wrong_type, bad_box, notes)
AUDIT = {
    (K, 1, "Text"):   (6, 10, 0, 0, "cover is a form: short labels/fields mostly unboxed"),
    (K, 1, "Title"):  (0, 2, 0, 1, "FORM 10-K and Apple Inc. missed; SEC header box cuts COMMISSION"),
    (K, 1, "Table"):  (0, 1, 1, 0, "securities table missed; Nasdaq column boxed as Text"),
    (K, 10, "Text"):  (5, 0, 0, 2, "straddling box merges end of para 4 + start of para 5; para 5 last 3 lines unboxed"),
    (K, 10, "Title"): (0, 1, 0, 0, "bold italic risk-factor heading missed"),
    (K, 20, "Text"):  (2, 0, 1, 4, "None. labeled Title; cybersecurity paragraphs mis-cut and merged"),
    (K, 20, "Title"): (5, 0, 0, 0, "Item headings and italic risk heading all found"),
    (K, 22, "Text"):  (2, 1, 0, 1, "repurchase intro cut off; 'common stock is traded' missed"),
    (K, 22, "Title"): (2, 1, 1, 0, "Item 5 labeled Text; 'Purchases of Equity...' missed"),
    (K, 22, "Table"): (0, 0, 1, 2, "repurchase table labeled Figure; header boxed as Text; Table box over empty space"),
    (K, 32, "Text"):  (1, 1, 0, 0, "scale caption '(In millions...)' missed"),
    (K, 32, "Title"): (1, 1, 0, 0, "statement title missed"),
    (K, 32, "Table"): (0, 0, 6, 1, "table box covers numbers only; row labels split into 6 Text boxes"),
    (K, 34, "Text"):  (0, 2, 0, 0, "scale caption and 'See accompanying Notes' missed"),
    (K, 34, "Title"): (1, 3, 0, 0, "statement title and liabilities heading missed"),
    (K, 34, "Table"): (0, 1, 3, 0, "balance sheet not detected; 3 label groups as Text; bottom half unboxed"),
    (K, 50, "Text"):  (1, 1, 0, 3, "sliver box; last line cut; '(in millions)' line cut"),
    (K, 50, "Title"): (0, 0, 0, 1, "note heading cuts off 'Data'"),
    (K, 50, "Table"): (0, 0, 3, 1, "one box merges 3 tables, numbers only; labels as 3 Text boxes"),
    (Q, 4, "Title"):  (1, 2, 0, 1, "statement title merged with caption in one Text box; PART I and Item 1 missed"),
    (Q, 4, "Table"):  (1, 0, 0, 0, "full statement incl. row labels"),
    (Q, 15, "Text"):  (4, 0, 0, 3, "sliver box; line cut; heading + paragraph merged"),
    (Q, 15, "Title"): (3, 1, 1, 0, "Note 8 labeled Text; 'Restricted Stock Units' missed"),
    (Q, 15, "Table"): (0, 2, 6, 1, "RSU table numbers only; 2 small tables undetected; rows as Text/Title"),
    (Q, 28, "Text"):  (0, 3, 1, 1, "None. labeled Title; footnotes and 'Not applicable.' missed"),
    (Q, 28, "Title"): (0, 2, 2, 0, "Item 3/4 labeled Text; Item 2 and section heading missed"),
    (Q, 28, "Table"): (0, 0, 1, 1, "repurchase table labeled Figure; header boxed separately"),
}
PAGES = [(K, p) for p in (1, 10, 20, 22, 32, 34, 50)] + [(Q, p) for p in (4, 15, 28)]
CLASSES = ["Text", "Title", "List", "Table", "Figure"]

out = Path("prototyping/shravya/layout_audit.csv")
totals = {c: [0, 0, 0, 0] for c in CLASSES}
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["stem", "page", "class", "correct", "missed", "wrong_type", "bad_box", "notes"])
    for stem, page in PAGES:
        for c in CLASSES:
            *counts, notes = AUDIT.get((stem, page, c), (0, 0, 0, 0, ""))
            w.writerow([stem, page, c, *counts, notes])
            totals[c] = [t + n for t, n in zip(totals[c], counts)]

print(f"{'class':7} correct missed wrong bad  correct_rate")
for c, (ok, miss, wrong, bad) in totals.items():
    n = ok + miss + wrong + bad
    print(f"{c:7} {ok:7} {miss:6} {wrong:5} {bad:4}  {ok}/{n}" + (f" = {ok / n:.0%}" if n else ""))
print("saved", out)
