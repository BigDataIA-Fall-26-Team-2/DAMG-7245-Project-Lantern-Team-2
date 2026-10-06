# XBRL validation (Part 11)

Every number on Apple's three primary statements, in both filings, is checked against the filing's own XBRL.
Issues #38 (fact extraction), #39 (mapping and comparison), #57 (this report), #49 (Docling path, pending).

**Result (traditional path): 388 table cells, 328 match (84.5%), 60 sign, 0 other. Value agreement 388 / 388.
Every non-match has a diagnosed cause.** All numbers below come from `notebooks/xbrl_validation.ipynb`
(executed outputs) and `data/xbrl/comparison_traditional.csv` unless stated.

## How it works

1. `python src/xbrl.py --input data/rendered/manifest.csv --output data/xbrl` loads each unpacked iXBRL filing with
   Arelle and writes `data/xbrl/facts.csv`: 1,553 numeric facts after de-duplication.
2. `python src/xbrl.py compare --path traditional --tables data/tables` maps each PDF row label to a concept and
   grades every cell. Mapping layers, in order, recorded per cell: **manual** (`config/label_map.yaml`, 63 lines) ->
   **label** (the filing's own `_lab.xml`) -> **fuzzy** (difflib, cutoff `xbrl.fuzzy_cutoff` = 0.85 in `params.yaml`).
   A label that points to several concepts is resolved by value; if none agrees it is marked `ambiguous`, never guessed.
3. Tolerance = 0.5 × 10^(−decimals) of the XBRL fact (500,000 for facts in millions). Statuses: `match`, `sign`,
   `scale_x1e{N}`, `mismatch`, `pdf_missing`, `xbrl_missing`.

Statement pages (`xbrl.statement_pages` in `params.yaml`): 10-K p32 income, p34 balance, p36 cash flow;
10-Q p4 income, p6 balance, p9 cash flow.

## Match rate per statement and extraction path

| Path | Statement | Cells | match | sign | other | Match rate | Value agreement |
|---|---|---:|---:|---:|---:|---:|---:|
| traditional | Income | 133 | 133 | 0 | 0 | **100.0%** | 100% |
| traditional | Balance | 110 | 110 | 0 | 0 | **100.0%** | 100% |
| traditional | Cash flow | 145 | 85 | 60 | 0 | **58.6%** | 100% |
| traditional | **All** | **388** | **328** | **60** | **0** | **84.5%** | **100%** |
| docling | all | — | — | — | — | *pending #49* | — |

Per filing (traditional):

| Filing | Statement | Cells | match | sign | Match rate |
|---|---|---:|---:|---:|---:|
| 10-K FY2025 | Income | 57 | 57 | 0 | 100.0% |
| 10-K FY2025 | Balance | 54 | 54 | 0 | 100.0% |
| 10-K FY2025 | Cash flow | 87 | 51 | 36 | 58.6% |
| 10-Q Q3 FY2026 | Income | 76 | 76 | 0 | 100.0% |
| 10-Q Q3 FY2026 | Balance | 56 | 56 | 0 | 100.0% |
| 10-Q Q3 FY2026 | Cash flow | 58 | 34 | 24 | 58.6% |

The cash-flow sign share is identical in both filings because the same 12 lines are presented negated in every period.

Mapping methods (traditional): 315 cells manual, 73 label linkbase, 0 fuzzy, 0 ambiguous, 0 none. All 73 label-layer
cells agree with XBRL by value (notebook section 7).

## Every non-match and its cause

All 60 non-match cells are `sign`: 12 cash-flow lines × 3 periods in the 10-K and 2 in the 10-Q. In each, the PDF prints
the amount negated (in parentheses) while XBRL stores it with its natural sign, and the filing's presentation linkbase
(`_pre.xml`) marks the concept with a negated preferred label. The `cause` column carries this automatically;
the notebook's acceptance check finds **0 non-match cells without a cause**.

One period shown per line (10-Q, 9M ended 2026-06-27, in USD millions); all periods are in the CSV.

| Path | PDF label | Concept | PDF value | XBRL value | Status | Mapping | Diagnosed cause / fix |
|---|---|---|---:|---:|---|---|---|
| trad. | Adjustments…: Other | OtherNoncashIncomeExpense | −2,037 | 2,037 | sign | manual | presentation (negated label); fixed mapping, see #3 below |
| trad. | Changes in operating assets…: Accounts receivable, net | IncreaseDecreaseInAccountsReceivable | 8,316 | −8,316 | sign | label | presentation (negated label) |
| trad. | Changes…: Vendor non-trade receivables | IncreaseDecreaseInOtherReceivables | 5,671 | −5,671 | sign | label | presentation (negated label) |
| trad. | Changes…: Inventories | IncreaseDecreaseInInventories | −5,461 | 5,461 | sign | label | presentation (negated label) |
| trad. | Changes…: Other current and non-current assets | IncreaseDecreaseInOtherOperatingAssets | −16,266 | 16,266 | sign | label | presentation (negated label) |
| trad. | Investing activities: Purchases of marketable securities | PaymentsToAcquireAvailableForSaleSecuritiesDebt | −48,752 | 48,752 | sign | label | presentation (negated label) |
| trad. | Investing activities: Payments for acquisition of property, plant and equipment | PaymentsToAcquirePropertyPlantAndEquipment | −6,799 | 6,799 | sign | manual | presentation (negated label) |
| trad. | Investing activities: Other | PaymentsForProceedsFromOtherInvestingActivities | −1,780 | 1,780 | sign | manual | presentation (negated label) |
| trad. | Financing activities: Payments for taxes related to net share settlement of equity awards | PaymentsRelatedToTaxWithholdingForShareBasedCompensation | −6,462 | 6,462 | sign | label | presentation (negated label) |
| trad. | Financing activities: Payments for dividends and dividend equivalents | PaymentsOfDividends | −11,778 | 11,778 | sign | manual | presentation (negated label) |
| trad. | Financing activities: Repurchases of common stock | PaymentsForRepurchaseOfCommonStock | −62,094 | 62,094 | sign | manual | presentation (negated label) |
| trad. | Financing activities: Repayments of term debt | RepaymentsOfLongTermDebt | −8,146 | 8,146 | sign | label | presentation (negated label) |

Key matched lines, for reference:

| Path | PDF label | Concept | PDF value | XBRL value | Status | Mapping |
|---|---|---|---:|---:|---|---|
| trad. | Net income (10-K, FY ended 2025-09-27) | NetIncomeLoss | 112,010 | 112,010 | match | manual |
| trad. | Total assets (10-K and 10-Q, 2025-09-27) | Assets | 359,241 | 359,241 | match | manual |
| trad. | Non-current assets: Intangible assets, net (10-Q, 2026-06-27) | aapl:IntangibleAssetsNetExcludingGoodwillNoncurrent | 20,342 | 20,342 | match | manual |
| trad. | Cash…, beginning balances (10-Q, 9M ended 2026-06-27) | CashCashEquivalentsRestrictedCash… at 2025-09-27 | 35,934 | 35,934 | match | manual |
| trad. | Cash…, ending balances (10-Q, 9M ended 2026-06-27) | CashCashEquivalentsRestrictedCash… at 2026-06-27 | 39,544 | 39,544 | match | manual |

## What broke and how it was fixed

The first run covered the 10-K income and balance sheet and all three 10-Q statements: **271 / 301 cells matched**.
Every one of the 30 non-matches was diagnosed and fixed before the 10-K cash flow (p36) was added:

| # | Cells | Before | Cause category | What was wrong | Fix |
|---|---:|---|---|---|---|
| 1 | 2 | mismatch | mapping | Intangible assets mapped to `IntangibleAssetsNetExcludingGoodwill` (25,417M, the total) instead of the non-current part (20,342M). The concept-exists check could not catch this; only the value comparison did | concept corrected in `config/label_map.yaml` |
| 2 | 2 | xbrl_missing | extension concept | the correct concept is Apple's own `aapl:IntangibleAssetsNetExcludingGoodwillNoncurrent`; map lines were assumed `us-gaap` | optional `prefix` per map line |
| 3 | 2 | mismatch | mapping | the generic label "Other" on the operating line matched Apple's investing concept (1,780M vs −2,037M), a silent wrong mapping | the three "Other" lines added to the manual map; `ambiguous` rule so a shared label is never guessed |
| 4 | 4 | xbrl_missing | period alignment | beginning/ending cash balances are instants printed in "9M ended" columns | a duration column also tries its end date and its opening date (the day before it starts), keeping the one that agrees by value |
| 5 | 22 | sign | presentation convention | not an error | cause filled automatically from `_pre.xml` |

After the fixes the same 301 cells gave **277 match + 24 sign**; adding the 10-K cash flow gave the totals above.
Every fix has a regression test in `tests/test_xbrl_compare.py`, and a teeth check (sign check and opening-instant lookup
broken on purpose) made 4 of them fail.

No non-match was caused by OCR, table structure, normalization or rounding: the table extractor reads the PDF text
layer of the six statement pages (no OCR involved), and every extracted value agreed with XBRL in magnitude.

**One more finding.** The line "Financing activities: Proceeds from/(Repayments of) commercial paper" resolves to
`ProceedsFromRepaymentsOfCommercialPaper` in two periods and to `ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess`
in one: Apple tagged the same printed line with a different concept in one year. Disambiguation by value picked the right
concept each time, and all three cells match (notebook section 7).

## Limitations

- The Docling path is not compared yet (#49); its row above is pending and the notebook will include it automatically.
- Only the three primary statements are compared; the shareholders' equity statement (10-K p35) and comprehensive income (p33) are not.
- Cash-flow total rows carry the previous subsection's prefix from Part 2 section tracking (e.g. "Changes in operating
  assets and liabilities: Cash generated by operating activities"); they are mapped as printed and all match.
- The manual map is specific to Apple's two filings; automated mapping across filings is the stretch goal (#82).
- The fuzzy layer was never needed on this corpus; it is covered only by a unit test.
- Arelle needs internet on its first load to cache the US-GAAP taxonomy.

## Reproduce

```
python src/xbrl.py --input data/rendered/manifest.csv --output data/xbrl
python src/xbrl.py compare --path traditional --tables data/tables
python -c "import nbformat; from nbclient import NotebookClient; p='notebooks/xbrl_validation.ipynb'; nb=nbformat.read(p, 4); NotebookClient(nb, timeout=180, kernel_name='python3', resources={'metadata': {'path': 'notebooks'}}).execute(); nbformat.write(nb, p)"
```
