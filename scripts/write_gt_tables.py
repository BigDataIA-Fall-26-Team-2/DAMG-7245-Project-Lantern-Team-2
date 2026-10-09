"""Write the two Part 9 ground truth table CSVs, as reconciled.

The figures were keyed by hand from the 150 DPI page images (see
CONVENTIONS.md), independently by two people (issue #27), and reconciled:
113 cells compared, 0 value disagreements, 0 printed-form disagreements. The
only differences were the scope of the section prefix on row labels, which
the reconciliation settled in favour of the written convention (prefix only a
label that repeats on the page), and two bare heading rows on 10-Q p6 that
the second transcription omitted. The two original transcriptions are kept in
data/ground_truth/double_keyed/.

This script only reshapes the keyed grid into one line per cell and applies
the per-row scale. It exists so the files are written without passing through
a spreadsheet, which reinterprets the value column as scientific notation and
silently rounds every figure to three significant digits.
"""

import csv
from pathlib import Path

OUT_DIR = Path("data/ground_truth")

M = 1_000_000
K = 1_000
ONE = 1

SHARE_LABEL = (
    "Common stock and additional paid-in capital, $0.00001 par value: "
    "50,400,000 shares authorized; 14,608,963 and 14,773,260 shares issued "
    "and outstanding, respectively"
)

P32_COLS = ["September 27, 2025", "September 28, 2024", "September 30, 2023"]
P32_ROWS = [
    ("Net sales:", None, ["", "", ""]),
    ("Net sales: Products", M, ["$ 307,003", "$ 294,866", "$ 298,085"]),
    ("Net sales: Services", M, ["109,158", "96,169", "85,200"]),
    ("Total net sales", M, ["416,161", "391,035", "383,285"]),
    ("Cost of sales:", None, ["", "", ""]),
    ("Cost of sales: Products", M, ["194,116", "185,233", "189,282"]),
    ("Cost of sales: Services", M, ["26,844", "25,119", "24,855"]),
    ("Total cost of sales", M, ["220,960", "210,352", "214,137"]),
    ("Gross margin", M, ["195,201", "180,683", "169,148"]),
    ("Operating expenses:", None, ["", "", ""]),
    ("Research and development", M, ["34,550", "31,370", "29,915"]),
    ("Selling, general and administrative", M, ["27,601", "26,097", "24,932"]),
    ("Total operating expenses", M, ["62,151", "57,467", "54,847"]),
    ("Operating income", M, ["133,050", "123,216", "114,301"]),
    ("Other income/(expense), net", M, ["(321)", "269", "(565)"]),
    ("Income before provision for income taxes", M, ["132,729", "123,485", "113,736"]),
    ("Provision for income taxes", M, ["20,719", "29,749", "16,741"]),
    ("Net income", M, ["$ 112,010", "$ 93,736", "$ 96,995"]),
    ("Earnings per share:", None, ["", "", ""]),
    ("Earnings per share: Basic", ONE, ["$ 7.49", "$ 6.11", "$ 6.16"]),
    ("Earnings per share: Diluted", ONE, ["$ 7.46", "$ 6.08", "$ 6.13"]),
    ("Shares used in computing earnings per share:", None, ["", "", ""]),
    ("Shares used in computing earnings per share: Basic", K,
     ["14,948,500", "15,343,783", "15,744,231"]),
    ("Shares used in computing earnings per share: Diluted", K,
     ["15,004,697", "15,408,095", "15,812,547"]),
]

P6_COLS = ["June 27, 2026", "September 27, 2025"]
P6_ROWS = [
    ("ASSETS:", None, ["", ""]),
    ("Current assets:", None, ["", ""]),
    ("Cash and cash equivalents", M, ["$ 39,544", "$ 35,934"]),
    ("Current assets: Marketable securities", M, ["22,855", "18,763"]),
    ("Accounts receivable, net", M, ["31,398", "39,777"]),
    ("Vendor non-trade receivables", M, ["27,509", "33,180"]),
    ("Inventories", M, ["11,092", "5,718"]),
    ("Other current assets", M, ["17,420", "14,585"]),
    ("Total current assets", M, ["149,818", "147,957"]),
    ("Non-current assets:", None, ["", ""]),
    ("Non-current assets: Marketable securities", M, ["84,118", "77,723"]),
    ("Property, plant and equipment, net", M, ["51,431", "49,834"]),
    ("Intangible assets, net", M, ["20,342", "11,093"]),
    ("Other non-current assets", M, ["77,557", "72,634"]),
    ("Total non-current assets", M, ["233,448", "211,284"]),
    ("Total assets", M, ["$ 383,266", "$ 359,241"]),
    ("LIABILITIES AND SHAREHOLDERS' EQUITY:", None, ["", ""]),
    ("Current liabilities:", None, ["", ""]),
    ("Accounts payable", M, ["$ 64,525", "$ 69,860"]),
    ("Other current liabilities", M, ["62,259", "66,387"]),
    ("Deferred revenue", M, ["9,538", "9,055"]),
    ("Commercial paper", M, ["1,997", "7,979"]),
    ("Current liabilities: Term debt", M, ["11,007", "12,350"]),
    ("Total current liabilities", M, ["149,326", "165,631"]),
    ("Non-current liabilities:", None, ["", ""]),
    ("Non-current liabilities: Term debt", M, ["71,340", "78,328"]),
    ("Other non-current liabilities", M, ["55,080", "41,549"]),
    ("Total non-current liabilities", M, ["126,420", "119,877"]),
    ("Total liabilities", M, ["275,746", "285,508"]),
    ("Commitments and contingencies", None, ["", ""]),
    ("Shareholders' equity:", None, ["", ""]),
    (SHARE_LABEL, M, ["100,702", "93,568"]),
    ("Retained earnings/(Accumulated deficit)", M,
     ["11,326", "(14,264)"]),
    ("Accumulated other comprehensive loss", M,
     ["(4,508)", "(5,571)"]),
    ("Total shareholders' equity", M, ["107,520", "73,733"]),
    ("Total liabilities and shareholders' equity", M, ["$ 383,266", "$ 359,241"]),
]


def to_value(raw, scale):
    if raw == "" or scale is None:
        return ""
    s = raw.replace("$", "").replace(",", "").strip()
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    n = float(s) * scale
    if negative:
        n = -n
    return str(int(n)) if n == int(n) else repr(n)


def write(name, cols, rows):
    path = OUT_DIR / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row_label", "col_label", "raw", "value"])
        n = 0
        for label, scale, raws in rows:
            for col, raw in zip(cols, raws):
                w.writerow([label, col, raw, to_value(raw, scale)])
                n += 1
    print(path, n)


OUT_DIR.mkdir(parents=True, exist_ok=True)
write("AAPL_10K_20250927_p32_t1.gt.csv", P32_COLS, P32_ROWS)
write("AAPL_10Q_20260627_p6_t1.gt.csv", P6_COLS, P6_ROWS)