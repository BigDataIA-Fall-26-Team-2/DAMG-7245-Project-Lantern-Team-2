"""P3 tuning: how many layout blocks survive at each score threshold, on a mix of page types."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, "src")
import pdfplumber
from layout import load_model, detect_page, load_params

# A mix of page types: cover, prose, statements, notes
PAGES = {"AAPL_10K_20250927": [1, 10, 20, 32, 34, 50], "AAPL_10Q_20260627": [2, 4, 15]}
THRESHOLDS = [0.5, 0.4, 0.3, 0.25, 0.2, 0.1]

model = load_model()
params = load_params()["layout"]
out = Path("prototyping/shravya/threshold_sweep.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["stem", "page", "threshold", "blocks", "types"])
    for stem, pages in PAGES.items():
        with pdfplumber.open(f"data/rendered/{stem}.pdf") as pdf:
            for n in pages:
                for t in THRESHOLDS:
                    _, _, recs = detect_page(model, pdf.pages[n - 1], {**params, "score_threshold": t})
                    w.writerow([stem, n, t, len(recs), ",".join(sorted(r["block_type"] for r in recs))])
                print(f"{stem} p{n}: done")
print("saved", out)