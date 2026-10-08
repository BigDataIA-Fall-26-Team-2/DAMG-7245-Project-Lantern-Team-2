# Part 9: accuracy, regression gates and drift

Owner: Guna. Issue #22 (sampling), #27 (double-keyed tables).

To reproduce:

```
python src/export.py
python src/evaluate.py
pytest tests/test_quality.py -q
```

Outputs: `reports/metrics.json`, `reports/plots/drift.png`.

## 1. Ground truth

We have 20 sample slots, 10 per filing. The strata for each slot was decided
**before** looking at any parser output. 18 different pages were typed, because
the multi-column fixture is filling that slot for both filings and it was typed
only once.

| Stratum | 10-K pages | 10-Q pages |
|---|---|---|
| Cover | 1 | 1 |
| Prose | 5, 6 | 17, 22 |
| Primary statements | 32, 34, 36 | 4, 6, 9 |
| Notes with dense tables | 40, 43 | 11, 16 |
| Multi-column | `tests/fixtures/multicolumn.pdf` p1 | same fixture |
| Scanned | `tests/fixtures/scanned.pdf` p1 | same fixture |

Both filings dont have any multi-column prose page or scanned page, so these
two strata are taken from the committed fixtures, the brief allows this.

For the dense notes we picked the hardest pages on purpose (10-K p40 is first
page of Note 4 Financial Instruments, p43 has four tables, 10-Q p16 is four
stacked seven-column segment tables), not the easy note pages. An easy page
tells nothing about where the errors are coming from.

Every page was typed by eye from the 150 DPI PNG images in
`data/ground_truth/pages/`, made with `pdftoppm`. No parser output, no text
layer and no copy paste was used anywhere. This is important: the text layer of
the rendered PDF has a token `g6614` where the Apple logo is on 10-K page 1, a
human never sees it. If the ground truth was made by editing parser output, it
would have that token also and pdfplumber would look perfect against itself.

The conventions are written in `data/ground_truth/CONVENTIONS.md`, before the
typing started. The replacements that matter for scoring are applied **same way
on both sides** in `src/evaluate.py`: registered-trademark and trademark marks
removed, curly quotes changed to ASCII, em and en dashes changed to a hyphen,
ballot-box characters changed to `[X]` and `[ ]`. At scoring time we only do
lower-case, collapse whitespace and strip. **We dont remove punctuation on
purpose**, because then `(1,234)` becomes `1234` and the sign error gets hidden,
and that is the one error a financial pipeline cannot hide.

### Tables

Two statement tables are keyed by hand: 10-K p32 (income statement) and 10-Q p6
(balance sheet), saved as four columns `row_label, col_label, raw, value`. `raw`
is the cell as printed, `value` is the figure in full units after applying the
per-row scale. The scale is per row and not per table, the page itself says
that: 10-K p32 header says "In millions, except number of shares, which are
reflected in thousands, and per-share amounts". If we used one scale for the
whole page, every share-count and per-share row would be wrong.

Row labels have a section prefix (`Net sales: Products` is different from
`Cost of sales: Products`) because four labels on p32 and two on p6 come twice
on the page. Without the prefix, one label plus one column label points to two
different cells, and twelve cells will get scored against wrong figures.

Both tables are also checked with arithmetic, separate from the metric: all
three columns of p32 add up from net sales to net income and both EPS figures,
and p6 balances in both periods with every subtotal adding up. If one digit was
typed wrong, one of these sums would break.

`scripts/write_gt_tables.py` changes the keyed grid into one line per cell and
applies the per-row scale. We need it because a spreadsheet silently corrupts
the file: Excel reads `307003000000` as `3.07E+11` and saves it back rounded to
three significant figures. That gave table cell F1 of exactly 0.0 with no error
message at all, and now `test_ground_truth_values_are_full_precision` guards it.

## 2. Measured accuracy

Baseline, `reports/metrics.json`, break mode `none`.

### By path, 16 scoreable pages

| Path | mean WER | mean CER | mean numeric-token F1 |
|---|---|---|---|
| Traditional (pdfplumber + Camelot + layout) | 0.4850 | 0.4582 | 0.7497 |
| Docling | 0.2149 | 0.2103 | 0.8633 |

Docling numbers are after the fix in finding 3. Before the fix the Docling
export had no tables and it scored 0.5314 WER and 0.3453 numeric F1. The managed
path (AWS Textract, Part 7) is scored only on the pages we sent to it, it is in
`reports/build_vs_buy.md`.

### By stratum, traditional path

| Stratum | pages | mean WER | worst WER | mean CER | mean numeric F1 | worst numeric F1 |
|---|---|---|---|---|---|---|
| Prose | 4 | 0.0840 | 0.1530 | 0.0795 | 0.7500 | 0.0000 |
| Cover | 2 | 0.4989 | 0.5465 | 0.4769 | 0.4916 | 0.4615 |
| Notes | 4 | 0.6003 | 0.7506 | 0.5361 | 0.5728 | 0.3357 |
| Statements | 6 | 0.6709 | 0.9202 | 0.6526 | 0.9536 | 0.9310 |

### The main result

Statement pages score **0.954 numeric-token F1** and **0.671 WER** at the same
time. These two numbers are not fighting each other, they measure different
things.

WER and CER care about order, so on a statement page they measure how much the
hypothesis follows the reading order of the page, not only if the words are
right. The high statement WER of the traditional path is mostly not a reading
error. It comes from the layout stage (finding 6): on 10-K p32 the layout Table
box covers only the figure columns, so the row labels on its left get exported
one more time as normal text blocks, and the statement title and units line
are lost.

Docling path shows this clearly. On p32 its table rows are exactly same as
traditional path, prefixes also same, but its WER is 0.208 and traditional is
0.726. So the table content is same, only the page structure around it is
different. An earlier version of this report said the gap is because the table
is one block and because of the section prefixes. The Docling comparison proved
that wrong, because Docling also has both and still scores much lower.

Numeric-token F1 dont care about order, so on the same pages it shows what we
actually want: 95% of the figures on the primary financial statements are read
correctly, and the hand-keyed cell comparison on p32 and p6 gives **precision,
recall and F1 all 1.0** (57/57 and 56/56 cells).

So the conclusion is: **WER is the right tool for prose, and numeric-token F1
plus table cell F1 are the right tools for tables.** The 0.485 overall average
dont describe any of them, thats why every number above is per stratum. If we
reported only the average, both the 0.084 prose result and the 0.954 statement
figure result would be hidden.

### Notes on some numbers

- Prose worst numeric F1 of 0.0 is because of a very small count: 10-K p6 has
  only two number-like tokens, missing one makes F1 zero. It is not the same
  kind of reading failure as the notes number.
- Cover pages get 0.50 WER mostly because of page furniture: the
  securities-registered table and the checkbox grid. The `[X]` folding on both
  sides is very important here, without it every checkbox line would mismatch.
- Notes worst numeric F1 of 0.336 is under-extraction, not misreading, see
  finding 2.

## 3. Regression gates and the failing run

`tests/test_quality.py` has the gates. Thresholds are set from the measured
baseline with some headroom, and each one writes in `params.yaml` the baseline
it came from, so if someone changes it later it is a visible decision and not
silent drift.

| Gate | Threshold | Baseline |
|---|---|---|
| Worst prose WER | <= 0.20 | 0.153 |
| Mean prose CER | <= 0.12 | 0.0795 |
| Mean numeric-token F1, all pages | >= 0.65 | 0.750 |
| Table cell F1, every GT table | >= 0.90 | 1.000 |
| Table value recall, every GT table | >= 0.90 | 1.000 |

Two gates are regression tests for real bugs Part 9 found, not imaginary ones:
`test_no_placeholder_table_bbox` and `test_table_extractor_matches_tables_log`.

### Proving the gates actually work

`src/evaluate.py --break <mode>` damages the hypothesis in one named way before
scoring. Run on the same inputs:

| Mode | p32 cell F1 | p6 cell F1 | statement numeric F1 | statement mean WER |
|---|---|---|---|---|
| `none` (baseline) | 1.0000 | 1.0000 | 0.9536 | 0.6709 |
| `no-scale` | 0.1053 | 0.0000 | 0.9536 | 0.6709 |
| `drop-parens` | 0.9474 | 0.9643 | 0.7671 | 0.7295 |
| `drop-words` | 1.0000 | 1.0000 | 0.9536 | 0.6283 |

`no-scale` acts like we forgot the per-row scale and carried the printed figure
as if it is already in full units. Table cell metric falls to 0.105 and 0.000.
`drop-parens` acts like we lost the parentheses-as-negative rule, statement
numeric F1 falls from 0.954 to 0.767 and the worst statement WER goes above
1.0, which is possible because of insertions.

Note that `no-scale` dont change WER or numeric F1, because that break only
changes the scaled `rows` and the text hypothesis is built from `raw_cells`.
This is a real limit of the text metrics: a scale error is invisible to WER and
only the cell comparison catches it. Thats also the reason why the cell
comparison is there.

`drop-words` is the check for the text side. It deletes every fifth word of
every text block and dont touch tables, like a parser that silently loses text.
Prose worst WER goes from 0.153 to 0.3153 and prose mean CER from 0.0795 to
0.2571, so both prose gates fail, and all eleven other gates pass and both table
cell scores stay 1.0. So each gate fails only on the damage it is guarding,
nothing else. The run is saved in `reports/teeth_check_prose_failing_run.txt`.

We did two separate things to the text gates, dont mix them. The break mode is
what proves they work: the old loose gates (0.25 and 0.20) also would have
failed on it. Tightening to 0.20 and 0.12 is a separate change, it makes them
catch smaller damage, the headroom over the worst prose page is now 0.047
instead of 0.097.

Statement-page WER actually *goes down* with `drop-words`, from 0.6709 to
0.6283. Deleting words can make the hypothesis closer to the reference only if
it had extra words, so this separately confirms finding 6: the traditional
statement pages have their row labels two times.

The table failing run is saved in `reports/`:

```
python src/evaluate.py --break no-scale --out reports/metrics_break_no_scale.json
set LANTERN_METRICS=reports/metrics_break_no_scale.json
pytest tests/test_quality.py -q > reports/teeth_check_failing_run.txt
set LANTERN_METRICS=
```

and the prose one same way:

```
python src/evaluate.py --break drop-words --out reports/metrics_break_drop_words.json
set LANTERN_METRICS=reports/metrics_break_drop_words.json
pytest tests/test_quality.py -q > reports/teeth_check_prose_failing_run.txt
set LANTERN_METRICS=
```

## 4. Drift signals

`reports/plots/drift.png`, three panels across the two pipeline versions
(traditional and Docling):

1. **Text block length distribution.** The two paths chunk the same documents
   differently. If this distribution shifts between pipeline versions, it is the
   cheapest early warning that some upstream change changed the segmentation.
2. **Mean WER by stratum**, both paths.
3. **Mean numeric-token F1 by stratum**, both paths. The two paths are most
   different on statements here, because of finding 6.

`reports/metrics.json` also saves, per filing, the share of pages sent to OCR.
This is the drift signal that moves first if the rendering or the OCR trigger
changes.

## 5. Reproducibility and metrics diff

The evaluate stage is in `dvc.yaml`, `reports/metrics.json` is declared as
metrics and `reports/plots/drift.png` as a plot (both `cache: false`, so they
stay in git where this report links them):

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

```
dvc repro -s evaluate
dvc metrics show
```

We tested `dvc metrics diff` with the `no-scale` break mode: score the broken
hypothesis into the workspace, diff it with the committed baseline, then score
the normal one again. The output is in `reports/metrics_diff_no_scale.txt`. It
shows exactly the metrics the break should move and nothing else: table cell F1
falls from 1.0 to 0.1053 on 10-K p32 and from 1.0 to 0.0 on 10-Q p6, on both
traditional and Docling paths, and every text metric is same.

```
python src/evaluate.py --break no-scale
dvc metrics diff > reports/metrics_diff_no_scale.txt
python src/evaluate.py
```

The stage also reads `data/managed` for the Part 7 side-by-side, which is
tracked on the Part 7 branch, so it is added to this stage's deps there.

## 6. Findings

All these came out of the measurement and not just from looking at the output,
thats the point of Part 9.

**1. Placeholder table bounding boxes (fixed, after a second review).** 10-Q
pages 6 and 9 had `bbox [0.0, 0.0, 1.0, 1.0]`, a one point square at the page
origin. The tables stage found a table on a page where the layout stage found
no Table region, and the export just fell back to a constant. The records were
schema valid but the provenance claim was false, and the schema cannot catch
that.

The first fix used the union of every layout block on the page. Peer review
showed that was also wrong: on a page where the only detection is a heading,
the union is just the heading box, so the table pointed at the heading in a
narrow rectangle that looks precise. The union is honest only when every box in
it is a real Table detection.

Now the export marks every table bbox as `detected` (paired one-to-one with a
layout Table region), `union` (many Table regions and the count dont match the
table CSVs, every box in the union is a table) or `page` (no Table region at
all, so the box is the full page, taken from the rendered PDF size). Every
approximate box is written to `reports/export_bbox_fallback.csv`. Across both
filings **11 of 55 table records have an approximate box: 8 unions and 3 full
pages.** The three full-page ones are 10-Q pages 6, 9 and 28, an earlier check
that looked only at sampled pages found two of them. The Docling tables added in
finding 3 go through the same marking, against Docling's own Table boxes: 6 of
their 54 have a union box, logged with the stem suffix `.docling`.
`tests/test_exports_bbox.py` covers all three cases, also the heading-only page
from review.

Running the evaluation again after the change moved no metric, because on 10-Q
p6 the table sorts to the top of the page with both boxes. The fix corrects the
provenance claim, not the scores.

**2. Under-extraction on stacked-table pages.** 10-Q p11 and p16 each give only
one table block of four rows. p16 has four stacked seven-column segment tables,
so most of its cells are never extracted. This is the worst notes numeric F1,
0.336. The cause is before the export, in table detection, raised with Part 2.

**3. The Docling export dropped every Docling table (fixed, found in review).**
Part 4 writes Docling tables to `data/docling/tables/` in the same contract CSV
format as Part 2, 54 tables across both filings. The export's Docling path was
skipping every Docling Table record and never reading those CSVs, so the
Docling JSONL was text only. An earlier version of this finding blamed Docling,
but it was the export. Shravya pointed it out in review on #111.

Now the export reads `data/docling/tables/` with the same function that reads
`data/tables/`, so both paths go to the schema by the same route and get scored
on same kind of input. The effect:

| Docling path | before | after |
|---|---|---|
| mean WER | 0.5314 | 0.2149 |
| mean numeric-token F1 | 0.3453 | 0.8633 |
| raw cell F1, 10-K p32 | not scored | 1.0000 |
| raw cell F1, 10-Q p6 | not scored | 1.0000 |

The traditional path numbers did not move, so the change only added the
missing tables.

**4. Column headers are not recovered on irregular tables.** 10-K p32 gives
real headers (`FY ended 2025-09-27`), but 10-K p22, the share-repurchase table,
gives `col1, col2, col3`. So the cell comparison matches on column *position*
and not on the header string. If we matched on the header, every cell on p22
would be wrong even where the figure is read correctly, so we would be
measuring header recovery but calling it reading accuracy. Header recovery
should be its own metric, it is not there yet.

**5. Text-block `extractor_version` had the layout model string (fixed).** Text
blocks said `extractor: pdfplumber` with
`extractor_version: lp://efficientdet/PubLayNet/tf_efficientdet_d0`. The layout
record gives `extractor_version: null` and a separate `model` field, and the
adapter was falling back to `model`, which is a version string of a different
tool. Same bug on the table side was caught in review, this one was caught
here. Fixed in f7e3ae2, now it reports the installed pdfplumber version.

**6. The layout Table box covers only the figure columns (raised with Part 3).**
On 10-K p32 the traditional Table box goes from x = 362 to x = 603 on a page
about 612 points wide, so it covers the figures but not the row labels. The
labels are outside it and get exported again as List and Text blocks at x = 6
to 12 (`Net sales: Products Services Total net sales...`), and the statement
title and the units line (`In millions, except...`) are missing. Docling's box
for the same table goes from x = 5.5 to x = 607 and has none of these
duplicates. This is the main reason for the traditional statement WER (section
2). It is a layout detection issue, not a reading or export error, and it also
matters later: a chunk with a column of row labels and no figures is just noise
for retrieval.

**7. Clipped closing parentheses on 10-Q p6 (raised with Part 2).** Rows 24 and
25 of the p6 table have `raw_cells` `(14,264` and `(5,571`: the closing
parenthesis, which is just past the rightmost column, got cut off. The
normaliser still gave the correct negative values, so the scaled cell F1 was
1.0 and hid it. The raw cell metric, which compares printed figures, caught it
at 0.9818. It depends on the extractor: that page went through pdfplumber-text,
and p32's `(565)` in same position went through Camelot and was fine. Docling
and Textract both read the two cells correctly.

## 7. Scope and what these numbers dont claim

### Scope we chose

- One company, two filings: that is the pinned scope of the assignment. Apple
  filings are very clean, so these numbers are an optimistic bound and we are
  not saying this is general accuracy.
- 16 of the 20 sample slots are scored. The multi-column and scanned fixture
  pages have hand-made ground truth but no pipeline output, because the fixtures
  were not run through the stages. So these two strata are not measured, and
  the CI gates in `tests/test_quality.py` run on local data and not on the
  committed fixtures. To close this, the fixtures need to be run through the
  stages.
- Table ground truth is two tables out of 32 extracted from the 10-K and 23
  from the 10-Q, which is the brief's minimum. Cell F1 of 1.0 is measured on two
  statement tables, it is not a number for the whole pipeline.
- `tests/fixtures/statement.pdf` is a one-page extract of 10-K p32, so the
  fixture ground truth in `tests/fixtures/gt/` repeats a sampled page and dont
  add a new one. It is there so the comparison can run on a machine without the
  filings, which CI needs, it is not separate evidence.

### Open items

- **`data/ground_truth/` is in git and not DVC-tracked**, against the
  deliverable list. When we committed it DVC was not there on this machine. It
  is hand-keyed source material and not regenerable output, so git is ok, but
  it is not what was asked.
- **Layout Table boxes** (finding 6) and **clipped parentheses** (finding 7)
  are raised with Parts 3 and 2, not fixed here.
- The 18 pages are typed by one person. The two statement tables are
  double-keyed as per the Lab 9 protocol (#27): keyed separately by Guna and
  Dhruvi, 113 cells compared, 0 value disagreements.
- 10-Q page 7 is not in the sample: it is blank but it wrongly goes to OCR,
  against Part 1's own acceptance criteria. WER on a blank page means nothing,
  but the page is a real defect and it affects the OCR-share drift signal.