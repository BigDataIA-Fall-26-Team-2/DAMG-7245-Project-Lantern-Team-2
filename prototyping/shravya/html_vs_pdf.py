"""P4 task 2: what did PDF rendering change? Compare Docling's tables from the original HTML vs the rendered PDF."""
import glob, re
import pandas as pd

num = lambda f: int(re.search(r"_t(\d+)_raw", f).group(1))
files = sorted(glob.glob("data/docling/AAPL_10K_20250927_html_t*_raw.csv"), key=num)
empty, widths, net = 0, [], []
for f in files:
    df = pd.read_csv(f, dtype=str).fillna("")
    cells = [c.strip() for r in df.values.tolist() for c in r]
    if not any(cells):
        empty += 1
    widths.append(df.shape[1])
    for r in df.values.tolist():
        if r and r[0].strip().lower() == "net income":
            net.append((num(f), [c for c in dict.fromkeys(c.strip() for c in r[1:]) if c]))
print("HTML tables:", len(files), "| completely empty:", empty)
print("columns per table: median", sorted(widths)[len(widths) // 2], "| max", max(widths))
for n, vals in net[:3]:
    print(f"t{n} Net income ->", vals[:6])
pdf_w = [pd.read_csv(f).shape[1] for f in glob.glob("data/docling/AAPL_10K_20250927_p*_t*_raw.csv")]
print("PDF tables:", len(pdf_w), "| columns per table: median", sorted(pdf_w)[len(pdf_w) // 2], "| max", max(pdf_w))
