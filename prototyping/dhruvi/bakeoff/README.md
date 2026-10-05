# Part 2 table bake-off (Issue #17)

Five extraction methods were run on four statement pages of the rendered Apple filings and scored against
40 hand-checked cells (10 per page). Everything here is reproducible from the files in this folder.

## How to reproduce

```bash
python prototyping/dhruvi/bakeoff/bakeoff.py --input data/rendered --output prototyping/dhruvi/bakeoff/results
python prototyping/dhruvi/bakeoff/score_cells.py --gt prototyping/dhruvi/bakeoff/gt_cells.csv --input prototyping/dhruvi/bakeoff/results --output prototyping/dhruvi/bakeoff/results
```

Pages (rendered-PDF page numbers, Letter, Playwright 1.55.0): 10-K FY2025 income p32 and balance sheet p34;
10-Q Q3 FY2026 income p4 and balance sheet p6. Printed footer page numbers differ (e.g. p32 prints "29").

Ground truth (`gt_cells.csv`): 10 cells per page, values transcribed exactly as printed from the rendered page
images in `pages/` (transcribed by Claude from screenshots of these images, checked by Dhruvi against the pages),
never from parser output. Cells cover all period columns, a `$` row, a per-share row, subtotals and
parenthesized negatives. A cell is correct only if the row label matches (n-th occurrence) and the value in the
expected column matches as exact text.

## Results per page and method

`accuracy`/`whitespace` are Camelot's own parsing report (pdfplumber has none). Source: `results/summary.csv`,
`results/cell_scores.csv`, per-cell detail in `results/cell_check.csv`.

| stem              |   page | kind    | method          | status    |   n_tables | largest_shape   | accuracy   | whitespace   |   seconds | cells correct   |
|:------------------|-------:|:--------|:----------------|:----------|-----------:|:----------------|:-----------|:-------------|----------:|:----------------|
| AAPL_10K_20250927 |     32 | income  | camelot-lattice | no_tables |          0 | –               | –          | –            |     0.496 | 0/10            |
| AAPL_10K_20250927 |     32 | income  | camelot-stream  | ok        |          1 | 27x7            | 99.64      | 47.09        |     0.056 | 10/10           |
| AAPL_10K_20250927 |     32 | income  | camelot-network | ok        |          1 | 22x6            | 100.0      | 42.42        |     0.044 | 0/10            |
| AAPL_10K_20250927 |     32 | income  | camelot-hybrid  | ok        |          1 | 22x6            | 100.0      | 42.42        |     0.364 | 0/10            |
| AAPL_10K_20250927 |     32 | income  | pdfplumber-text | ok        |          1 | 61x9            | –          | –            |     0.121 | 10/10           |
| AAPL_10K_20250927 |     34 | balance | camelot-lattice | no_tables |          0 | –               | –          | –            |     0.361 | 0/10            |
| AAPL_10K_20250927 |     34 | balance | camelot-stream  | ok        |          1 | 17x5            | 98.35      | 44.71        |     0.033 | 4/10            |
| AAPL_10K_20250927 |     34 | balance | camelot-network | ok        |          1 | 41x5            | 97.35      | 48.78        |     0.062 | 10/10           |
| AAPL_10K_20250927 |     34 | balance | camelot-hybrid  | ok        |          5 | 41x5            | 97.35      | 48.78        |     0.419 | 10/10           |
| AAPL_10K_20250927 |     34 | balance | pdfplumber-text | ok        |          1 | 79x8            | –          | –            |     0.144 | 10/10           |
| AAPL_10Q_20260627 |      4 | income  | camelot-lattice | no_tables |          0 | –               | –          | –            |     0.444 | 0/10            |
| AAPL_10Q_20260627 |      4 | income  | camelot-stream  | ok        |          1 | 27x9            | 98.77      | 48.15        |     0.048 | 10/10           |
| AAPL_10Q_20260627 |      4 | income  | camelot-network | ok        |          1 | 22x8            | 98.45      | 42.05        |     0.054 | 0/10            |
| AAPL_10Q_20260627 |      4 | income  | camelot-hybrid  | ok        |          1 | 22x8            | 98.45      | 42.05        |     0.416 | 0/10            |
| AAPL_10Q_20260627 |      4 | income  | pdfplumber-text | ok        |          1 | 61x10           | –          | –            |     0.157 | 10/10           |
| AAPL_10Q_20260627 |      6 | balance | camelot-lattice | no_tables |          0 | –               | –          | –            |     0.354 | 0/10            |
| AAPL_10Q_20260627 |      6 | balance | camelot-stream  | ok        |          1 | 18x5            | 98.84      | 44.44        |     0.039 | 5/10            |
| AAPL_10Q_20260627 |      6 | balance | camelot-network | ok        |          2 | 34x3            | 96.26      | 19.61        |     0.066 | 7/10            |
| AAPL_10Q_20260627 |      6 | balance | camelot-hybrid  | ok        |          5 | 21x5            | 95.36      | 49.52        |     0.418 | 7/10            |
| AAPL_10Q_20260627 |      6 | balance | pdfplumber-text | ok        |          1 | 81x9            | –          | –            |     0.145 | 9/10            |

## Overall (40 cells per method)

`label_found`: the method kept the row label. `value_anywhere`: the expected value appears anywhere in the output.

| method          |   correct |   label_found |   value_anywhere |   cells |   cell accuracy |
|:----------------|----------:|--------------:|-----------------:|--------:|----------------:|
| camelot-lattice |         0 |             0 |                0 |      40 |           0     |
| camelot-stream  |        29 |            29 |               31 |      40 |           0.725 |
| camelot-network |        17 |            17 |               40 |      40 |           0.425 |
| camelot-hybrid  |        17 |            17 |               40 |      40 |           0.425 |
| pdfplumber-text |        39 |            40 |               39 |      40 |           0.975 |

## By table type (cells correct out of 10)

| method          | income AAPL_10K_20250927   | balance AAPL_10K_20250927   | income AAPL_10Q_20260627   | balance AAPL_10Q_20260627   |
|:----------------|:---------------------------|:----------------------------|:---------------------------|:----------------------------|
| camelot-lattice | 0/10                       | 0/10                        | 0/10                       | 0/10                        |
| camelot-stream  | 10/10                      | 4/10                        | 10/10                      | 5/10                        |
| camelot-network | 0/10                       | 10/10                       | 0/10                       | 7/10                        |
| camelot-hybrid  | 0/10                       | 10/10                       | 0/10                       | 7/10                        |
| pdfplumber-text | 10/10                      | 10/10                       | 10/10                      | 9/10                        |

## Rulings per page

| stem              |   page | kind    |   h_rulings |   v_rulings |
|:------------------|-------:|:--------|------------:|------------:|
| AAPL_10K_20250927 |     32 | income  |          38 |          57 |
| AAPL_10K_20250927 |     34 | balance |          30 |          54 |
| AAPL_10Q_20260627 |      4 | income  |          50 |          76 |
| AAPL_10Q_20260627 |      6 | balance |          28 |          56 |

## Findings

1. **Lattice found no tables on any page.** The pages show horizontal underlines under subtotals but no visible
   vertical lines. pdfplumber reports 54-76 "vertical" thin rectangles per page, but they are 1.5 pt wide,
   about one row tall, repeated each row at the column edges, and not visible in the rendered page, so raw
   vertical counts overstate real rulings. Lattice ran without any Ghostscript error.
2. **Income statements:** stream and pdfplumber-text scored 10/10 on both filings. Network and hybrid scored
   0/10 although every value was present: the row-label column came back empty.
3. **Balance sheets:** network 10/10 (10-K) and 7/10 (10-Q); hybrid the same cells but split into 5 tables;
   pdfplumber-text 10/10 and 9/10; stream only 4/10 and 5/10.
4. **Camelot's accuracy score is not correctness:** network reports 100.0 on the 10-K income page and gets 0/10 cells.

## Diagnosed failures

| Failure | Cause |
|---|---|
| Stream misses every cell from "Total current liabilities" down on both balance sheets | Stream only extracts the ASSETS half; the "LIABILITIES AND SHAREHOLDERS' EQUITY" heading ends its table (17-18 rows on ~40-line pages) |
| Network/hybrid miss "Retained earnings/(Accumulated deficit)" on 10-Q p6 | The label text is absent from the output while the numbers are present (same label loss as on income pages) |
| pdfplumber-text gives `(14,264` instead of `(14,264)` on 10-Q p6 | The closing parenthesis is dropped (outside the last detected column); the label is also split mid-word into 3 cells |

## Caveats

- The scorer re-joins label fragments split across cells (pdfplumber splits words such as `earn|ings`), so
  pdfplumber's score assumes the same label re-joining step in `src/tables.py`.
- `value_anywhere` is weak evidence for totals that repeat: "Total liabilities and shareholders' equity" always
  equals "Total assets", so the value can be "found" in the wrong row.
- Four pages from one company; results may differ for filings with visible grid lines.

## Implications for `src/tables.py` (#29, #30)

- Count only visible rulings for the `min_rulings` lattice heuristic; on these pages lattice should never be chosen.
- No single Camelot flavor wins both table types, so pick per table by a quality score (rows with a label and
  numbers) against `accept_score`, with pdfplumber-text as a strong candidate.
- Normalization must treat an unmatched `(` as negative, drop `$` tokens, and re-join split label fragments.
