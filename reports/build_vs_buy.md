# Part 7: Build vs buy, managed document AI

Owner: Guna. Provider: AWS Textract, `AnalyzeDocument` (synchronous), features
`TABLES` and `LAYOUT`, region `us-east-1`.

To reproduce, no credentials and no API calls needed:

```
python src/managed/textract.py          # managed.enabled: false, reads cache only
python src/evaluate.py                  # side-by-side scores in reports/metrics.json
```

## 1. What we sent

Three pages, the brief limit is ten:

| Page | Why |
|---|---|
| 10-K p32 (income statement) | Clean statement page, hand-keyed table ground truth |
| 10-Q p6 (balance sheet) | Second clean statement page, hand-keyed table ground truth |
| `tests/fixtures/scanned.pdf` p1 | The scanned fixture, where a managed service should earn its price |

Each page is rasterised at 150 DPI with `pdftoppm`, same resolution as the
ground truth images, and sent as image bytes. Responses are cached in
`data/managed/<hash>.json`, the key is first 32 hex characters of the sha256 of
the rendered PNG. The cache is written before the response is mapped, so a
mapping bug never makes us pay for a second call. This actually happened once:
the schema rejected the fixture's `doc_id`, we fixed the mapping, and the re-run
came fully from cache.

## 2. Mapping into the schema

`src/managed/textract.py` maps Textract's block graph into the Appendix B
schema: `LAYOUT_*` blocks to the schema block types, `TABLE` and `CELL` blocks
to the schema table object with `raw_cells`. Block ids use the band
`p{NNNN}_b500` to `b899`, so they cant collide with layout blocks (`b001` up) or
table blocks (`b901` up). Output is one `{stem}.blocks.jsonl` per document, 30
schema-valid records in total (6 for p32, 6 for p6, 18 for the scanned page).

Two representation differences we handled in the metric and not in the data,
because they are not reading errors:

- Textract gives row labels bare (`Products`), but the traditional path puts
  the section before repeated labels (`Net sales: Products`). The metric removes
  a prefix only when it exactly matches one of that table's own heading rows
  (see `reports/eval.md`).
- Textract does no scale normalisation. So we added **raw cell F1**, it compares
  printed figures without scaling, so Textract gets scored on reading and not
  on a normalisation step it never says it does.

## 3. Side-by-side results, same pages

| Page | Path | WER | CER | Numeric F1 | Raw cell F1 |
|---|---|---|---|---|---|
| 10-K p32 | Traditional | 0.7262 | 0.6753 | 0.9500 | 1.0000 |
| | Docling | 0.2083 | 0.1947 | 0.9500 | 1.0000 |
| | Textract | 0.0476 | 0.0284 | 0.9767 | 1.0000 |
| 10-Q p6 | Traditional | 0.8216 | 0.8014 | 0.8467 | 0.9818 |
| | Docling | 0.2535 | 0.3035 | 0.9677 | 1.0000 |
| | Textract | 0.0423 | 0.0210 | 0.9697 | 1.0000 |
| Scanned p1 | Tesseract (Part 1) | 0.0225 | 0.0107 | 0.9333 | n/a |
| | Textract | 0.0188 | 0.0101 | 0.9333 | n/a |

Docling numbers include its tables. An earlier version of this table showed
Docling at 0.0 numeric F1, because the export was dropping Docling's tables.
That got fixed in #111 (`reports/eval.md`, finding 3), and now Docling scores
1.0 raw and scaled cell F1 on both statement tables. Numeric F1 counts repeated
numbers (`reports/eval.md`, finding 8), so it is a bit lower than in earlier
versions for every path.

### How to read this table

**Dont read the WER column as "Textract is fifteen times more accurate".** Most
of the traditional WER on these pages is a layout effect, not misreading: its
layout Table box covers only the figure columns, so the row labels get exported
one more time as text and the statement title is lost (`reports/eval.md`,
finding 6). Docling shows this. Its table rows are exactly same as traditional,
but its WER on p32 is 0.208 and traditional is 0.726. Part of the gap that is
left to Textract (0.208 vs 0.048) is likely the section prefix on repeated row
labels (`Net sales: Products`), both open-source paths have it and Textract
dont. We did not measure that split.

The reading metrics show the real story. Numeric F1 on p32 is 0.950 for both
open-source paths and 0.977 for Textract. On p6 it is 0.847 traditional, 0.968
Docling and 0.970 Textract. So Docling is within about three points of Textract
on both pages (only 0.2 on p6). The traditional path is 12 points behind on p6,
because it loses some of the figures that the page prints more than once
(`reports/eval.md`, finding 8). Raw cell F1 is perfect for all three paths on
p32.

### Errors Textract fixes

- **Clipped parentheses on 10-Q p6.** The traditional path's `raw_cells` for
  rows 24 and 25 have `(14,264` and `(5,571`: the closing parenthesis, which is
  just past the rightmost column, got cut by the extraction box. Part 2's
  normaliser still gave the correct negative values, so the scaled metric was
  1.0 and hid it, the raw metric caught it (0.9818). Textract read both cells
  correctly, **and Docling also did** (raw cell F1 1.0), so this error dont need
  a paid service, an open-source path in the same pipeline already avoids it.
  It depends on the extractor: p32's `(565)` is in same position, went through
  Camelot and not pdfplumber-text, and it was fine. Raised with Part 2.
- **Literal column headers.** On p32 Textract gave the header exactly as
  printed, `September 27, 2025`. The traditional headers on that page are
  normalised (`FY ended 2025-09-27`), and on irregular tables like 10-K p22
  Camelot gives none (`col1, col2, col3`). We did not run Textract on p22, so we
  dont know if it gets headers on irregular tables.

### Errors Textract brings in

- **It OCRs text that the PDF already has exactly.** The synchronous API takes
  an image, so on digital pages Textract reads the characters again from
  pixels. On both p32 and p6 it read the footer separator `|` as a capital `I`:
  `Apple Inc. I 2025 Form 10-K I 29`. pdfplumber reads the same character
  exactly from the text layer. On a born-digital filing, paying a service to
  OCR text you already have means paying to add errors.
- **No scale normalisation, no section context.** Both have to be built again
  later, exactly like for the open-source path.

### The scanned page

On the scanned fixture, Textract gets 0.019 WER, 0.010 CER and 0.93 numeric F1.
Part 1's Tesseract on the same page gets 0.023 WER, 0.011 CER and **the same
0.93 numeric F1**. So on this page the free OCR is only 0.4 points of WER
behind Textract and exactly same on numbers. The Tesseract number comes from
the fixture gates (`tests/test_fixture_quality.py`, `reports/eval.md` section
3), so it is measured again in CI on every PR.

This matters for the recommendation. A scan was supposed to be the place where
a managed service clearly earns its price, and on this scan it does not. To be
fair to Textract, this fixture is a clean scan: straight, good resolution,
simple layout. We did not test the harder scans where OCR usually breaks
(skewed or noisy pages, low DPI, tables inside a scan), and thats where
Textract could still be clearly better.

## 4. Fallback design

Textract is an optional fallback, same flow as the tutorial: open-source parse
first, if a page's OCR confidence or a table's score is below threshold, check
the cache, on a miss call the API only if `managed.enabled` is true, otherwise
keep the open-source result and flag the page.

`params.yaml`:

```yaml
managed:
  provider: aws_textract
  enabled: false          # default: dvc repro runs with no credentials
  region: us-east-1
  features: ["TABLES", "LAYOUT"]
  cache_dir: data/managed
  dpi: 150
  trigger:
    min_ocr_conf: 0.75
    min_table_score: 0.50
```

With `enabled: false` the code reads cache hits and makes no API calls, so the
pipeline runs on any machine. The entry point for the parsing and table stages
is `fallback_blocks()` in `src/managed/textract.py`.

The call site is `managed_fallback()` in `src/tables.py` (Part 2's stage), it
runs for every page after the best table is chosen. It fires only when a page
has a real table, means at least `tables.min_numeric_rows` (3) rows with
numbers, and that table scores below `managed.trigger.min_table_score` (0.50).
The rule uses Part 2's own setting and dont add a new one.

The result of every check is saved in a new `fallback` column at the end of
`data/tables/log/tables_log.csv`:

| Value | Meaning |
|---|---|
| empty | No check needed: no real table, or the table scored well |
| `used` | The managed answer was used, written to `data/tables/managed/<stem>_p<page>.blocks.jsonl`, and the export puts it in the final output |
| `miss` | Nothing cached and `managed.enabled` is false, so the open-source result is kept |
| `error` | The check could not run (for example, no `pdftoppm`), the stage continues |

The check never raises. A machine without `pdftoppm` or AWS credentials still
finishes the tables stage, thats what keeps `dvc repro` working with the
fallback disabled. Part 2's own outputs are not touched: the full stage still
writes the same 32 tables with the same winning methods.
`tests/test_managed_fallback.py` covers the five cases: no table, an empty
candidate, a good score, a cache miss, and a check that fails.

Three things changed after review on #116:

1. **The Textract table now reaches the final output, and replaces the bad
   one.** Before, the tables stage wrote it to `data/tables/managed/` and said
   `used`, but the export never read that folder, so a successful fallback
   changed nothing in the exported data. The rule now: a page with a managed
   answer is a page where Part 2's own table scored below the trigger, so Part
   2's table there is the low-quality result and the Textract table replaces
   it. Never both, so the same table never comes two times. If Part 2 wrote no
   table on that page, the Textract one fills the gap. This is in
   `managed_table_blocks()` and `merge_managed_tables()` in `src/export.py`,
   and every replaced page is logged in `reports/export_managed_tables.csv`
   (stem, page, which block was replaced, which managed block came in), so the
   provenance is visible outside the records also. `tests/test_export_managed.py`
   forces a low-score page with a cache hit and checks the export changes and
   the page ends with exactly one table. The tables stage also deletes an old
   managed answer for a page before checking it again, same like it does for
   its own CSVs.
2. **The config the caller passes is the config that applies.** Before,
   `tables.py` took `--params` but `textract.py` read the root `params.yaml` by
   itself on import, so a caller could pass `managed.enabled: false` and still
   get an API call. Now `tables.py` passes its own params into
   `fallback_blocks()`, and the switch, cache folder, region, features and DPI
   all come from there. `textract.py` dont read any params file on import, if
   nothing is passed the service stays off. Tests mock the API and check that no
   call happens when the passed config says `enabled: false` even if another
   params file says `true`, once directly on `textract.py`
   (`tests/test_managed_config.py`) and once through the real boundary,
   `tables.managed_fallback()` into the real module
   (`tests/test_managed_fallback.py`).
3. **`boto3` is pinned and failures are not hidden.** `boto3==1.43.106` is now
   in `requirements.txt` (it matches the `botocore` that `dvc-s3` installs). The
   live call path is tested with a mocked `boto3` client, no AWS calls. And when
   a check fails, the real exception (for example a missing module) is saved in
   a new `fallback_error` column in `tables_log.csv`, not just the word
   `error`.

The OCR-confidence side of the trigger, inside Part 1's parsing stage, is not
wired. On these two filings only the table side is used.

The cache is tracked with `dvc add data/managed` (`data/managed.dvc`).
`src/managed`, `data/managed` and the `managed` params are dependencies of the
`tables` stage, and `data/managed` of the `evaluate` stage, so a change to the
cache, the code or the switch reruns whatever reads them. `dvc repro -s tables`
with `managed.enabled: false` finishes and writes the same 32 tables.

The team's S3 remote (`lantern-s3`) is there now, but `dvc push
data/managed.dvc` from this account gives 403 Forbidden: the bucket is in a
different AWS account from the one used for Textract. Until the cache is
pushed, a fresh clone cant `dvc pull` it, and because `tables` depends on
`data/managed`, `dvc repro` there stops at that stage. Pushing it is pending
with the Part 8 owner.

One known false trigger to fix before wiring the OCR side: 10-Q p7 is blank and
wrongly goes to OCR in Part 1. An OCR-confidence trigger built on that routing
would pay Textract to read a blank page.

### A false trigger the table side had, and how we found it

The first version fired when any table candidate scored below 0.50. When we ran
it on both filings, it fired on **45 of 91 pages**. Every one of them scored
exactly 0.0 with no numeric rows: prose pages, signature pages and so on, where
Camelot's stream mode returns an empty candidate. These are pages with no
table, not pages with a badly read table, a managed service has nothing to fix
there. If enabled, that rule would have sent half of every filing to Textract.
Asking for three numeric rows removed all 45, and a regression test now guards
this case.

## 5. Pricing

From the AWS Textract pricing page, checked 8 October 2026
(https://aws.amazon.com/textract/pricing/):

| Meter | First 1M pages / month | After 1M |
|---|---|---|
| `AnalyzeDocument`, Tables (OCR included) | $15.00 per 1,000 | $10.00 per 1,000 |
| `AnalyzeDocument`, Layout with Tables | included, no charge | included |
| `DetectDocumentText` (OCR only, no tables) | $1.50 per 1,000 | $0.60 per 1,000 |

Our call uses Tables plus Layout, AWS bills that as Tables only: **$0.015 per
page**. AWS worked examples are priced for US West (Oregon), we ran in
us-east-1, so check the regional number in the AWS Pricing Calculator before
quoting it to a client.

Free tier: three months for new customers, including 100 pages a month of
`AnalyzeDocument` with Tables and Layout.

**Measured spend for this part:** three pages, so $0.045 at list price, and
nothing if the account is still in its free tier window.


## 6. Cost at FinTrust's volume

Assumptions, each one written so it can be replaced:

- 5,000 filings a year at about 100 pages each, the tutorial's planning number:
  **500,000 pages a year**, about 41,700 a month, all inside the first price
  tier. Our two filings average 45.5 pages (61 and 30), so this is a
  conservative upper bound.
- Self-hosted compute: $0.17 per 1,000 pages, the tutorial's anchor (a $0.40/h
  VM at 1.5 s per page), engineering time not included. Part 10's measured
  numbers are in `reports/benchmarks.md` and can replace this.
- Engineering time: $100 per hour, fully loaded. This is an assumption, not a
  measurement.

| Option | Per 1,000 pages | Per year, 500k pages | Per year, 227.5k pages (our 45.5 pp mix) |
|---|---|---|---|
| Textract on every page (Tables) | $15.00 | $7,500 | $3,413 |
| Textract OCR only (no tables) | $1.50 | $750 | $341 |
| Self-hosted open-source, compute only | $0.17 | $85 | $39 |
| Hybrid: Textract on 5% of pages | $0.75 blended | $375 | $171 |
| Hybrid: Textract on 1% of pages | $0.15 blended | $75 | $34 |

### The crossover

At 500,000 pages a year, Textract on every page costs about $7,400 more than
self-hosted compute. At $100 an hour, that difference buys roughly **74
engineer-hours a year, around an hour and a half a week**.

So for FinTrust the crossover is in maintenance time, not pages: if keeping the
open-source parsers working costs more than about 74 hours a year, Textract on
everything is cheaper, if it costs less, building is cheaper. In general,
managed wins when yearly maintenance cost is more than
`pages per year x (managed price - self-hosted price)`.

The hybrid mostly removes this question. Sending only the failing pages to
Textract keeps the managed bill in the tens to hundreds of dollars, and the
open-source path, which reads born-digital pages exactly, handles everything
else.

**Measured trigger rate on our two filings: 0 of 91 pages.** No page has a real
table scoring below 0.50, so on clean born-digital filings like Apple's the
table fallback costs nothing. So the 5% and 1% rows above are scenarios for
harder documents (other issuers, older filings, scans), not measurements, the
measured number for this corpus is 0%.

## 7. Data handling

From the AWS Textract FAQ, Data Privacy section, checked 8 October 2026
(https://aws.amazon.com/textract/faqs/):

- **Training use.** By default AWS may store and use document inputs to provide
  the service and to improve Textract and other Amazon AI technologies. To opt
  out you need an AWS Organizations AI services opt-out policy, it is an
  account-level setting, not a per-request flag.
- **Region.** Content is encrypted and stored at rest in the region where
  Textract is called, but unless the opt-out is there, some content may be
  stored in another region for service improvement. So region pinning depends
  on the opt-out.
- **Retention.** The FAQ gives no fixed retention period. Deleting stored
  inputs is by request to AWS Support.
- **Ownership and compliance.** The customer keeps ownership of content.
  Textract is HIPAA eligible, in scope for PCI, ISO and SOC, and can be called
  through a VPC endpoint so requests dont go over the public internet.

Questions that must be answered before any client document goes through this
path:

1. Is the AI services opt-out policy applied to the AWS Organization that owns
   the account? The account used here is a course account under an IAM user, we
   did not check if it has an opt-out.
2. Which region must client data stay in, and is that region guaranteed only
   with the opt-out?
3. What retention does the client's contract need, since AWS deletes on request
   and not on a schedule?
4. Does the client's data agreement allow a third-party processor at all?

For this project the risk is low: public SEC filings, already published on
EDGAR. The same pipeline on client documents would not be low risk, and the
`managed.enabled` flag should stay off for them until these four answers are
there.

## 8. Recommendation

Dont use Textract for everything. Use it as a fallback, on a small set of
pages, behind the flag.

**Where it belongs:** pages that fail the OCR or table trigger, and hard scans
(skewed, noisy, low resolution, tables inside the scan). On our clean scanned
fixture Tesseract was almost as good (0.023 vs 0.019 WER, same numeric F1), so
Textract is for the scans Tesseract cant read, not for every scan.

**Where it dont belong:** born-digital filings, which is almost all of
FinTrust's volume. There the text layer is exact, Docling reads statement
figures within about three points of Textract (0.2 points on p6, and it reads
the clipped parentheses that the traditional path loses), and Textract adds OCR
errors the text layer never had. The traditional path is behind on p6 (12
points), but thats a Part 2 problem with repeated figures that Docling, also
free, already avoids, so it is not a reason to pay for Textract.

**Lina's question, "Why not just use Textract for everything?", in five
sentences.** On accuracy, our free Docling path is within about three points of
Textract's numeric F1 on digital statement pages, it already avoids the reading
errors Textract fixed, and Textract adds errors there by OCRing text the PDF
already has exactly. On cost, Textract on every page is about $7,500 a year at
FinTrust's volume vs under $100 of compute, so it wins only if maintaining our
parsers costs more than about 74 engineer-hours a year. On lock-in, its output
is a provider-specific block graph that still needs mapping, scale
normalisation and section context, so buying it dont remove the engineering, it
just moves it. On data handling, client documents need an account-level
training opt-out, a region guarantee and a retention answer before even one
page is sent. So we keep the open-source path as default and send only hard
scans and failing pages to Textract, which is cheaper, more accurate where it
matters, and keeps client data at home unless we choose otherwise.

## 9. Limitations

- Three pages, two of them from one company's very clean filings. The
  statement-page comparison is strong evidence for clean digital tables and
  weak evidence for anything else.
- The Tesseract vs Textract comparison is one clean scanned page. Harder scans
  were not tested (section 3).
- The cache is not yet in the team's DVC remote (section 4).
- One provider only, Google Document AI and Azure were not run (stretch goal).
- The measured table trigger rate of 0 of 91 comes from one company's clean
  filings. The 5% and 1% fallback rates are scenarios for harder documents, not
  measurements (section 6).
- Only the table side of the trigger is wired. The OCR-confidence side in Part
  1 is not (section 4).
- Prices are list prices for the first tier, volume discounts and custom quotes
  are not considered.