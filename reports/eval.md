# Part 9: accuracy, regression gates and drift

Owner: Guna. Issue #22 (sampling), #27 (double-keyed tables).

Reproduce with:

```
python src/export.py
python src/evaluate.py
pytest tests/test_quality.py -q
```

Outputs: `reports/metrics.json`, `reports/plots/drift.png`.

## 1. Ground truth

Twenty sample slots, ten per filing, assigned to strata **before** any parser
output was looked at. Eighteen distinct pages were transcribed; the
multi-column fixture fills that slot for both filings and was typed once.

| Stratum | 10-K pages | 10-Q pages |
|---|---|---|
| Cover | 1 | 1 |
| Prose | 5, 6 | 17, 22 |
| Primary statements | 32, 34, 36 | 4, 6, 9 |
| Notes with dense tables | 40, 43 | 11, 16 |
| Multi-column | `tests/fixtures/multicolumn.pdf` p1 | same fixture |
| Scanned | `tests/fixtures/scanned.pdf` p1 | same fixture |

Neither filing contains a multi-column prose page or a scanned page, so those
two strata come from the committed fixtures, as the brief allows.

The dense-notes pages were chosen deliberately as the hardest in each filing
(10-K p40 is the first page of Note 4 Financial Instruments; p43 carries four
tables; 10-Q p16 is four stacked seven-column segment tables) rather than
lighter note pages. An easy page proves nothing about where the error budget
goes.

Transcription was by eye from 150 DPI PNG renderings in
`data/ground_truth/pages/`, produced with `pdftoppm`. No parser output, text
layer or clipboard extraction was used at any point. This is not a formality:
the rendered PDF's text layer contains the token `g6614` where the Apple logo
sits on 10-K page 1, an artifact no human reader sees. Ground truth built by
copy-editing parser output would have inherited that and would have made
pdfplumber look perfect against itself.

Conventions are written down in `data/ground_truth/CONVENTIONS.md`, before
transcription began. The substitutions that matter for scoring are applied
**identically to both sides** in `src/evaluate.py`: registered-trademark and
trademark marks stripped, typographic quotes folded to ASCII, em and en dashes
folded to a hyphen, ballot-box characters folded to `[X]` and `[ ]`.
Normalisation at scoring time is lower-casing, whitespace collapse and strip.
**Punctuation is deliberately not removed**, because removing it turns
`(1,234)` into `1234` and hides a sign error, which is the one error class a
financial pipeline cannot afford to hide.

### Tables

Two statement tables were keyed by hand: 10-K p32 (income statement) and 10-Q
p6 (balance sheet), stored as four columns `row_label, col_label, raw, value`.
`raw` is the cell as printed; `value` is the figure in full units after the
per-row scale. The scale is per row, not per table, and the page says so itself: 10-K p32 is
headed "In millions, except number of shares, which are reflected in thousands,
and per-share amounts". A single page-level scale would have been wrong on
every share-count and per-share row.

Row labels carry a section prefix (`Net sales: Products` as distinct from
`Cost of sales: Products`) because four labels on p32 and two on p6 appear
twice on the page. Without the prefix, a label plus column label identifies
two different cells and twelve cells would be scored against the wrong
figures.

Both hand-keyed tables were verified arithmetically, independently of the
metric: all three columns of p32 reconcile from net sales through to net
income and both EPS figures, and p6 balances in both periods with every
subtotal adding up. A single mis-keyed digit would have broken one of those
sums.

`scripts/write_gt_tables.py` reshapes the keyed grid into the one-line-per-cell
form and applies the per-row scale. It exists because a spreadsheet round trip
corrupts the file silently: Excel reinterprets `307003000000` as `3.07E+11`
and saves it back rounded to three significant figures. That produced a table
cell F1 of exactly 0.0 with no error message, and is now guarded by
`test_ground_truth_values_are_full_precision`.

## 2. Measured accuracy

Baseline, `reports/metrics.json`, break mode `none`.

### By path, 16 scoreable pages

| Path | mean WER | mean CER | mean numeric-token F1 |
|---|---|---|---|
| Traditional (pdfplumber + Camelot + layout) | 0.4850 | 0.4582 | 0.7497 |
| Docling | 0.5314 | 0.5157 | 0.3453 |

### By stratum, traditional path

| Stratum | pages | mean WER | worst WER | mean CER | mean numeric F1 | worst numeric F1 |
|---|---|---|---|---|---|---|
| Prose | 4 | 0.0840 | 0.1530 | 0.0795 | 0.7500 | 0.0000 |
| Cover | 2 | 0.4989 | 0.5465 | 0.4769 | 0.4916 | 0.4615 |
| Notes | 4 | 0.6003 | 0.7506 | 0.5361 | 0.5728 | 0.3357 |
| Statements | 6 | 0.6709 | 0.9202 | 0.6526 | 0.9536 | 0.9310 |

### The result that matters

Statement pages score **0.954 numeric-token F1** and **0.671 WER** at the same
time. Those two numbers are not in conflict; they measure different things.

WER and CER are order-sensitive. On a statement page a 29-row table is emitted
as one block, so the hypothesis presents the table as a unit while the
reference interleaves it in human reading order, and the alignment cost
dominates. The parser's row labels also carry the section prefix described
above, three printed words where the page prints one, so the word counts
cannot line up: 10-K p32 is 168 reference words against 208 hypothesis words,
and the surplus is exactly the repeated `Net sales:` and `Cost of sales:`
prefixes. Neither side is wrong. They represent the same page differently.

Numeric-token F1 is order-insensitive, so on the same pages it reports what we
actually care about: 95% of the figures on the primary financial statements are
read correctly, and the hand-keyed cell comparison on p32 and p6 returns
**precision, recall and F1 all 1.0** (57/57 and 56/56 cells).

The reading conclusion: **WER is the right instrument for prose, and
numeric-token F1 plus table cell F1 are the right instruments for tables.**
The 0.485 overall average describes neither, which is why every number above is
reported per stratum. Reporting only the average would have hidden both the
0.084 prose result and the 0.954 statement figure result.

### Caveats on specific numbers

- Prose worst-case numeric F1 of 0.0 is a small-denominator artifact: 10-K p6
  contains two number-like tokens, and missing one takes F1 to zero. It is not
  a reading failure of the same kind as the notes figure.
- Cover pages score 0.50 WER largely on page furniture: the securities-
  registered table and the checkbox grid. The `[X]` folding in both directions
  is load-bearing here; without it every checkbox line would mismatch.
- Notes worst-case numeric F1 of 0.336 is under-extraction, not misreading:
  see finding 2.

## 3. Regression gates and the failing run

`tests/test_quality.py` holds the gates. Thresholds are set from the measured
baseline with headroom, and each one records in `params.yaml` the baseline it
came from, so a later change is a visible decision rather than silent drift.

| Gate | Threshold | Baseline |
|---|---|---|
| Worst prose WER | <= 0.25 | 0.153 |
| Mean prose CER | <= 0.20 | 0.079 |
| Mean numeric-token F1, all pages | >= 0.65 | 0.750 |
| Table cell F1, every GT table | >= 0.90 | 1.000 |
| Table value recall, every GT table | >= 0.90 | 1.000 |

Two gates are regression tests for bugs Part 9 actually found, not
hypotheticals: `test_no_placeholder_table_bbox` and
`test_table_extractor_matches_tables_log`.

### Proving the gates have teeth

`src/evaluate.py --break <mode>` degrades the hypothesis in a named way before
scoring. Run on the same inputs:

| Mode | p32 cell F1 | p6 cell F1 | statement numeric F1 | statement mean WER |
|---|---|---|---|---|
| `none` (baseline) | 1.0000 | 1.0000 | 0.9536 | 0.6709 |
| `no-scale` | 0.1053 | 0.0000 | 0.9536 | 0.6709 |
| `drop-parens` | 0.9474 | 0.9643 | 0.7671 | 0.7295 |

`no-scale` simulates forgetting the per-row scale and carrying the printed
figure through as if already in full units. The table cell metric collapses to
0.105 and 0.000. `drop-parens` simulates losing the parentheses-as-negative
rule; statement numeric F1 falls from 0.954 to 0.767 and the worst statement
WER rises above 1.0, which insertions make possible.

Note that `no-scale` leaves WER and numeric F1 untouched, because that break
only alters the scaled `rows` while the text hypothesis is built from
`raw_cells`. That is a real limitation of the text metrics worth stating: a
scale error is invisible to WER and only the cell comparison catches it. It is
also the reason the cell comparison exists.

The failing run is recorded in `reports/`:

```
python src/evaluate.py --break no-scale --out reports/metrics_break_no_scale.json
set LANTERN_METRICS=reports/metrics_break_no_scale.json
pytest tests/test_quality.py -q > reports/teeth_check_failing_run.txt
set LANTERN_METRICS=
```

## 4. Drift signals

`reports/plots/drift.png`, three panels across the two pipeline versions
(traditional and Docling):

1. **Text block length distribution.** The two paths chunk the same documents
   differently; a shift in this distribution between pipeline versions is the
   cheapest early warning that an upstream change altered segmentation.
2. **Mean WER by stratum**, both paths.
3. **Mean numeric-token F1 by stratum**, both paths. This is where the two
   paths separate most sharply, for the reason in finding 3.

`reports/metrics.json` also records, per filing, the share of pages routed to
OCR, which is the drift signal that would move first if the rendering or the
OCR trigger changed.

## 5. Reproducibility and metrics diff

The evaluate stage is not yet wired into `dvc.yaml`, so `dvc repro evaluate`
and `dvc metrics diff` cannot be run here: DVC is set up by Part 8 in #103,
which is open at the time of writing, and running `dvc init` on this branch
would have collided with it. The stage definition has been handed to the Part 8
owner:

```yaml
  evaluate:
    cmd: python src/evaluate.py
    deps:
      - src/evaluate.py
      - data/ground_truth
      - data/export
    params:
      - evaluate
    metrics:
      - reports/metrics.json:
          cache: false
    plots:
      - reports/plots/drift.png:
          cache: false
```

The before-and-after that the diff should show is recorded here in the
meantime. Folding table content into the page hypothesis, so that a statement
page is compared as a whole page rather than as its headings alone:

| Metric | before | after | change |
|---|---|---|---|
| mean WER, traditional | 0.5153 | 0.4850 | -0.0303 |
| mean CER, traditional | 0.4885 | 0.4582 | -0.0303 |
| mean numeric-token F1, traditional | 0.3152 | 0.7497 | +0.4345 |

Reproduce by hand until the stage lands:

```
python src/export.py
python src/evaluate.py
pytest tests/test_quality.py -q
```

## 6. Findings

These came out of the measurement rather than from inspection, which is the
point of Part 9.

**1. Placeholder table bounding boxes (fixed).** 10-Q pages 6 and 9 carried
`bbox [0.0, 0.0, 1.0, 1.0]`, a one-point square at the page origin, because the
tables stage found a table on a page where the layout stage detected no Table
region and the export fell through to a constant. The records were schema
valid and the provenance claim was false, which is precisely the gap a schema
cannot close. Fixed in `src/export.py` to use the bounding box of all layout
blocks on the page: deliberately wider rather than confidently wrong.
Regression test added. Two of the 23 tables in the 10-Q have no corresponding
layout Table detection at all, which is a cross-stage gap raised with Parts 2
and 3.

**2. Under-extraction on stacked-table pages.** 10-Q p11 and p16 each yield a
single table block of four rows. p16 carries four stacked seven-column segment
tables, so the great majority of its cells are never extracted. This shows up
as the worst notes numeric F1, 0.336. The cause is upstream of the export, in
table detection, and is raised with Part 2.

**3. The Docling export is text-only.** Docling's own output contains 29 Table
blocks for the 10-Q, but the export's Docling path skips every Table block, so
the Docling JSONL has no tables. This is visible as the numeric F1 gap, 0.345
against 0.750, and means table cell F1 cannot be reported for the Docling path.
This is a known limitation accepted under the deadline rather than a measurement
artifact, and it is the first thing to close after submission.

**4. Column headers are not recovered on irregular tables.** 10-K p32 yields
real headers (`FY ended 2025-09-27`), while 10-K p22, the share-repurchase
table, yields `col1, col2, col3`. The cell comparison therefore keys on column
*position* rather than on the header string. Keying on the header would score
every cell on p22 as wrong even where the figure was read correctly, which
would measure header recovery while claiming to measure reading accuracy.
Header recovery is worth reporting as its own metric and is not yet.

**5. Text-block `extractor_version` carried the layout model string (fixed).**
Text blocks reported `extractor: pdfplumber` with
`extractor_version: lp://efficientdet/PubLayNet/tf_efficientdet_d0`. The layout
record supplies `extractor_version: null` and a separate `model` field, and the
adapter was falling back to `model`: a version string that describes a
different tool. The analogous bug on the table side was caught in review; this
one was caught here. Fixed in f7e3ae2 to report the installed pdfplumber
version.

## 7. Scope and what these numbers do not claim

### Deliberate scope

- One company, two filings: the pinned scope of the assignment. Apple's filings
  are unusually clean typographically, so these figures are an optimistic bound
  and are not offered as a general accuracy claim.
- Sixteen of the 20 sample slots are scored. The multi-column and scanned
  fixture pages have hand-made ground truth but no pipeline output, because the
  fixtures have not been run through the stages. Those two strata are therefore
  unmeasured, and the CI gates in `tests/test_quality.py` consequently run
  against local data rather than against the committed fixtures. Closing this
  requires the stage CLI work tracked in #103.
- Table ground truth is two tables out of 32 extracted from the 10-K and 23
  from the 10-Q, which is the brief's minimum. Cell F1 of 1.0 is measured on
  two statement tables and is not a pipeline-wide figure.
- `tests/fixtures/statement.pdf` is a one-page extract of 10-K p32, so the
  fixture ground truth in `tests/fixtures/gt/` duplicates a sampled page rather
  than adding one. It exists so that the comparison can run on a machine
  without the filings, which is what CI needs; it is not independent evidence.

### Open items

- **Docling table cell F1 is not reported.** Finding 3. The brief asks for both
  paths and this is the one requirement not met.
- **The text gates are loose and unproven.** Prose WER is gated at 0.25 against
  a measured 0.153, and neither break mode degraded prose text, so those gates
  have never been observed to fire. The table gates are proven; the text gates
  are not. Tightening them and adding a prose-damaging break mode is the next
  change.
- **`dvc repro evaluate` and `dvc metrics diff`**: see section 5.
- **`data/ground_truth/` is committed to git rather than DVC-tracked**, against
  the deliverable list, because DVC is not initialised on this machine and
  doing so would collide with #103. It is hand-keyed source material rather
  than regenerable output, so git is defensible, but it is not what was asked
  for and should move once #103 merges.
- **#27 double-keying** is complete on one side only.
- Transcription is by one person except for the two statement tables, which are
  double-keyed and reconciled per the Lab 9 protocol (#27).
- 10-Q page 7 is excluded from the sample: it is blank and wrongly triggers OCR
  against Part 1's own acceptance criteria. WER on a blank page is meaningless,
  but the page is a real defect and feeds the OCR-share drift signal.