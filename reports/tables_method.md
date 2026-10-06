# Part 2: Table extraction method (Issues #17, #29, #30, #37)

## Bake-off

Five methods were run on the income statement and balance sheet of both filings (10-K FY2025 p32/p34,
10-Q Q3 FY2026 p4/p6, rendered-PDF page numbers) and scored against 40 hand-checked cells transcribed from
the rendered page images. Full method, per-cell detail and diagnoses:
[`prototyping/dhruvi/bakeoff/README.md`](../prototyping/dhruvi/bakeoff/README.md).

**Cells correct by table type** (10 cells per page). Source: `prototyping/dhruvi/bakeoff/results/cell_scores.csv`

| method          | income 10K   | balance 10K   | income 10Q   | balance 10Q   |
|:----------------|:-------------|:--------------|:-------------|:--------------|
| camelot-lattice | 0/10         | 0/10          | 0/10         | 0/10          |
| camelot-stream  | 10/10        | 4/10          | 10/10        | 5/10          |
| camelot-network | 0/10         | 10/10         | 0/10         | 7/10          |
| camelot-hybrid  | 0/10         | 10/10         | 0/10         | 7/10          |
| pdfplumber-text | 10/10        | 10/10         | 10/10        | 9/10          |

**Overall.** `label_found` = row label kept; `value_anywhere` = value present anywhere in the output.

| method          |   cells correct (of 40) |   label_found |   value_anywhere |
|:----------------|------------------------:|--------------:|-----------------:|
| camelot-lattice |                       0 |             0 |                0 |
| camelot-stream  |                      29 |            29 |               31 |
| camelot-network |                      17 |            17 |               40 |
| camelot-hybrid  |                      17 |            17 |               40 |
| pdfplumber-text |                      39 |            40 |               39 |

**Shape and Camelot's own parsing accuracy.** Source: `prototyping/dhruvi/bakeoff/results/summary.csv`

| stem              |   page | kind    | method          |   n_tables | largest_shape   | accuracy   | cells   |
|:------------------|-------:|:--------|:----------------|-----------:|:----------------|:-----------|:--------|
| AAPL_10K_20250927 |     32 | income  | camelot-lattice |          0 | –               | –          | 0/10    |
| AAPL_10K_20250927 |     32 | income  | camelot-stream  |          1 | 27x7            | 99.64      | 10/10   |
| AAPL_10K_20250927 |     32 | income  | camelot-network |          1 | 22x6            | 100.0      | 0/10    |
| AAPL_10K_20250927 |     32 | income  | camelot-hybrid  |          1 | 22x6            | 100.0      | 0/10    |
| AAPL_10K_20250927 |     32 | income  | pdfplumber-text |          1 | 61x9            | –          | 10/10   |
| AAPL_10K_20250927 |     34 | balance | camelot-lattice |          0 | –               | –          | 0/10    |
| AAPL_10K_20250927 |     34 | balance | camelot-stream  |          1 | 17x5            | 98.35      | 4/10    |
| AAPL_10K_20250927 |     34 | balance | camelot-network |          1 | 41x5            | 97.35      | 10/10   |
| AAPL_10K_20250927 |     34 | balance | camelot-hybrid  |          5 | 41x5            | 97.35      | 10/10   |
| AAPL_10K_20250927 |     34 | balance | pdfplumber-text |          1 | 79x8            | –          | 10/10   |
| AAPL_10Q_20260627 |      4 | income  | camelot-lattice |          0 | –               | –          | 0/10    |
| AAPL_10Q_20260627 |      4 | income  | camelot-stream  |          1 | 27x9            | 98.77      | 10/10   |
| AAPL_10Q_20260627 |      4 | income  | camelot-network |          1 | 22x8            | 98.45      | 0/10    |
| AAPL_10Q_20260627 |      4 | income  | camelot-hybrid  |          1 | 22x8            | 98.45      | 0/10    |
| AAPL_10Q_20260627 |      4 | income  | pdfplumber-text |          1 | 61x10           | –          | 10/10   |
| AAPL_10Q_20260627 |      6 | balance | camelot-lattice |          0 | –               | –          | 0/10    |
| AAPL_10Q_20260627 |      6 | balance | camelot-stream  |          1 | 18x5            | 98.84      | 5/10    |
| AAPL_10Q_20260627 |      6 | balance | camelot-network |          2 | 34x3            | 96.26      | 7/10    |
| AAPL_10Q_20260627 |      6 | balance | camelot-hybrid  |          5 | 21x5            | 95.36      | 7/10    |
| AAPL_10Q_20260627 |      6 | balance | pdfplumber-text |          1 | 81x9            | –          | 9/10    |

## Preferred method per table type

**Income statements: Camelot stream**, which scored 10/10 cells on both filings with labels and values on the
same row, while network and hybrid scored 0/10 because they dropped the row-label column (even with Camelot
accuracy of 98.45-100.0). **Balance sheets: pdfplumber "text"**, which scored 10/10 and 9/10 and was the only
method that captured both halves of the sheet; stream stopped at the "LIABILITIES AND SHAREHOLDERS' EQUITY"
heading (4/10, 5/10). **Lattice is not used** on these filings: the pages have 0 visible vertical rulings
(the 54-76 vertical thin rectangles per page are all filled white, `(1.0, 1.0, 1.0)`), so lattice found no
table on any page. `src/tables.py` reaches the same choices without hard-coding table types: it scores every
candidate as label_ratio x coverage and, on the four statement pages, picks stream for both income statements
and pdfplumber-text for both balance sheets (table below, from `data/tables/log/tables_log.csv`).

| stem              |   page | kind    | method          |   score |   label_ratio |   coverage | runner_up       |   runner_up_score |   v_rulings |   skipped_rows |
|:------------------|-------:|:--------|:----------------|--------:|--------------:|-----------:|:----------------|------------------:|------------:|---------------:|
| AAPL_10K_20250927 |     32 | income  | camelot-stream  |   1     |         1     |          1 | pdfplumber-text |             1     |           0 |              0 |
| AAPL_10K_20250927 |     34 | balance | pdfplumber-text |   0.964 |         0.964 |          1 | camelot-network |             0.964 |           0 |              1 |
| AAPL_10Q_20260627 |      4 | income  | camelot-stream  |   1     |         1     |          1 | pdfplumber-text |             1     |           0 |              0 |
| AAPL_10Q_20260627 |      6 | balance | pdfplumber-text |   0.966 |         0.966 |          1 | camelot-network |             0.793 |           0 |              1 |

## Pipeline results (`src/tables.py`)

- Scanned all 91 pages of both filings in about 50 s on a MacBook Air (CPU); 32 tables written
  to `data/tables/{stem}_p{NNNN}_t1.csv`; winners: {'camelot-stream': 17, 'pdfplumber-text': 15}. Lattice was never chosen.
- **40/40 hand-checked cells correct** in the final CSVs, comparing normalized values (extraction and
  normalization together), and **0 duplicate row labels** on the four statement pages.
- Output follows `docs/CONTRACTS.md`: `row_label, col_label, raw, value, scale`. `row_label` carries the
  section (e.g. `Non-current assets: Marketable securities`); `col_label` is an ISO period
  (`FY ended 2025-09-27`, `3M ended 2026-06-27`, `2025-09-27`) to support XBRL period matching in Part 11.
- Thresholds live in `params.yaml` (`tables:` min_rulings, accept_score, min_numeric_rows, visible_max_gray);
  paths come in through `--input` / `--output`. Every page's decision is logged in `data/tables/log/tables_log.csv`.

## Normalization rules (#30)

| Rule | Example raw | value | scale |
|---|---|---|---|
| Strip `$` and thousands separators, apply caption scale ("In millions") | `$ 307,003` | 307,003,000,000 | 1,000,000 |
| Parentheses = negative | `(5,571)` | -5,571,000,000 | 1,000,000 |
| Unmatched parenthesis = negative (closing `)` dropped by the extractor) | `(14,264` | -14,264,000,000 | 1,000,000 |
| Per-share rows excepted from scaling | `7.46` (Earnings per share: Diluted) | 7.46 | 1 |
| Share counts use the caption's "reflected in thousands" | `14,656,110` | 14,656,110,000 | 1,000 |
| Footnote markers stripped | `1,234(1)` | 1,234 x scale | as caption |
| Only real dash glyphs = nil; blank spacer cells are never emitted | `—` | 0 | as caption |

`value` is in full units (number x scale) so it compares directly with XBRL; `raw` keeps the cell string exactly
as extracted. Unit tests for each rule: `tests/test_tables.py`.

## What broke and how we fixed it

| What broke | Evidence | Fix |
|---|---|---|
| Lattice found no tables | 0 tables on 4 pages; vertical thin rects all white | Count only visible rulings (`visible_max_gray: 0.9`) for the lattice gate |
| Network/hybrid scored 100.0 accuracy but 0/10 cells on income statements | Row-label column empty | Quality score includes label_ratio, so label-less tables lose |
| Stream truncated balance sheets at the liabilities heading | 17-18 rows on ~40-line pages | Quality score includes coverage (rows vs the best candidate) |
| pdfplumber dropped the closing parenthesis | raw `(14,264` | Unmatched `(` or `)` means negative |
| Column labels came out as `col1, col2` on pdfplumber tables | Dates split across cells; `27,` read as a number | Read the header from page text; number pattern accepts only real number shapes |
| "Non-current assets:" arrived as "current assets:", giving duplicate labels such as two `Current assets: Marketable securities` rows | Found by a duplicate-label check after 40/40 had already passed | Labels and sections now come from the page's own text lines, matched to each table row by its values |
| Validator reported a false failure for "Provision for income taxes" | Suffix match also hit "Income before provision for income taxes" | Exact label match after the section prefix |

The 40-cell sample did not touch the non-current rows, so it could not catch the duplicate-label bug; a
structural check (no repeated `row_label` per table) is now part of validation and of `tests/test_tables.py`.

## Limitations

- One table (the best-scoring) is written per page; pages with two separate tables keep only one.
- Rows whose number of values differs from the table's most common count are skipped and counted in
  `skipped_rows`, which loses rows in some mixed-column notes tables.
- Strict value matching means a table whose rows cannot be matched to page text lines yields no output:
  tables written fell from 42 to 32 when labels moved to page text. Statements are unaffected; some notes tables
  are dropped.
- Evaluated on one company, two filings and four statement pages.

## Reproduce

```bash
python src/tables.py --params params.yaml --input data/rendered --output data/tables
pytest -q tests/test_tables.py
```
