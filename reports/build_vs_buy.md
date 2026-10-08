# Part 7: Build vs buy, managed document AI

Owner: Guna. Provider: AWS Textract, `AnalyzeDocument` (synchronous), features
`TABLES` and `LAYOUT`, region `us-east-1`.

Reproduce, with no credentials and no API calls:

```
python src/managed/textract.py          # managed.enabled: false, reads cache only
python src/evaluate.py                  # side-by-side scores in reports/metrics.json
```

## 1. What was sent

Three pages, against a brief limit of ten:

| Page | Why |
|---|---|
| 10-K p32 (income statement) | Clean statement page, hand-keyed table ground truth |
| 10-Q p6 (balance sheet) | Second clean statement page, hand-keyed table ground truth |
| `tests/fixtures/scanned.pdf` p1 | The scanned fixture, where a managed service should earn its price |

Each page was rasterised at 150 DPI with `pdftoppm`, the same resolution as the
ground truth images, and sent as image bytes. Responses are cached in
`data/managed/<hash>.json`, keyed by the first 32 hex characters of the sha256 of
the rendered PNG. The cache is written before the response is mapped, so a
mapping bug never causes a second paid call. This happened once in practice: the
schema rejected the fixture's `doc_id`, the mapping was fixed, and the re-run was
served entirely from cache.

## 2. Mapping into the schema

`src/managed/textract.py` maps Textract's block graph into the Appendix B schema:
`LAYOUT_*` blocks to the schema's block types, `TABLE` and `CELL` blocks to the
schema's table object with `raw_cells`. Block ids use the band
`p{NNNN}_b500` to `b899`, so they cannot collide with layout blocks (`b001` up)
or table blocks (`b901` up). Output is one `{stem}.blocks.jsonl` per document, 30
schema-valid records in total (6 for p32, 6 for p6, 18 for the scanned page).

Two representation differences had to be handled in the metric rather than in
the data, because they are not reading errors:

- Textract prints row labels bare (`Products`), while the traditional path
  prefixes repeated labels with their section (`Net sales: Products`). The
  metric strips a prefix only when it exactly matches one of that table's own
  heading rows (see `reports/eval.md`).
- Textract does no scale normalisation. A **raw cell F1**, comparing printed
  figures unscaled, was added so Textract is scored on reading, not on a
  normalisation step it never claims to do.

## 3. Side-by-side results, identical pages

| Page | Path | WER | CER | Numeric F1 | Raw cell F1 |
|---|---|---|---|---|---|
| 10-K p32 | Traditional | 0.7262 | 0.6753 | 0.9500 | 1.0000 |
| | Docling | 0.2083 | 0.1947 | 0.9500 | 1.0000 |
| | Textract | 0.0476 | 0.0284 | 0.9844 | 1.0000 |
| 10-Q p6 | Traditional | 0.8216 | 0.8014 | 0.9412 | 0.9818 |
| | Docling | 0.2535 | 0.3035 | 0.9748 | 1.0000 |
| | Textract | 0.0423 | 0.0210 | 0.9839 | 1.0000 |
| Scanned p1 | Textract | 0.0188 | 0.0101 | 0.9600 | n/a |

Docling's figures include its tables. An earlier version of this table showed
Docling at 0.0 numeric F1, because the export dropped Docling's tables; that
was fixed in #111 (`reports/eval.md`, finding 3), and Docling now scores 1.0
raw and scaled cell F1 on both statement tables.

### How to read this table

**Do not read the WER column as "Textract is fifteen times more accurate".**
Most of the traditional path's WER on these pages is a layout effect, not
misreading: its layout Table box covers only the figure columns, so the row
labels are exported a second time as text and the statement title is lost
(`reports/eval.md`, finding 6). Docling is the control. Its table rows are
identical to the traditional path's, and its WER on p32 is 0.208 against 0.726.
Part of the remaining gap to Textract (0.208 against 0.048) is likely the
section prefix on repeated row labels (`Net sales: Products`), which both
open-source paths carry and Textract does not; that split was not measured.

The reading metrics tell the real story. Numeric F1 on p32 is 0.950 for both
open-source paths against 0.984 for Textract; on p6 it is 0.941 traditional,
0.975 Docling and 0.984 Textract. That is a gap of about one to four points, and raw
cell F1 is perfect for all three paths on p32.

### Errors Textract fixes

- **Clipped parentheses on 10-Q p6.** The traditional path's `raw_cells` for
  rows 24 and 25 hold `(14,264` and `(5,571`: the closing parenthesis, which
  hangs just past the rightmost column, was cut off by the extraction box.
  Part 2's normaliser still produced the correct negative values, so the scaled
  metric scored 1.0 and hid it; the raw metric caught it (0.9818). Textract
  read both cells intact, **and so did Docling** (raw cell F1 1.0), so this is
  not an error that needs a paid service: an open-source path in the same
  pipeline already avoids it. The defect is extractor-specific: p32's `(565)`
  sits in the same position, went through Camelot instead of pdfplumber-text,
  and survived. Raised with Part 2.
- **Literal column headers.** On p32 Textract returned the header exactly as
  printed, `September 27, 2025`. The traditional path's headers on that page are
  normalised (`FY ended 2025-09-27`), and on irregular tables such as 10-K p22
  Camelot returns none at all (`col1, col2, col3`). Textract was not run on p22,
  so whether it recovers headers on irregular tables is untested.

### Errors Textract introduces

- **It OCRs text that the PDF already contains exactly.** The synchronous API
  takes an image, so on digital pages Textract re-reads characters from pixels.
  On both p32 and p6 it read the footer separator `|` as a capital `I`:
  `Apple Inc. I 2025 Form 10-K I 29`. pdfplumber reads the same character
  exactly from the text layer. On a born-digital filing, paying a service to
  OCR text you already have is paying to add errors.
- **No scale normalisation, no section context.** Both must be rebuilt
  downstream, exactly as for the open-source path.

### The scanned page

Textract reads the scanned fixture almost perfectly: 0.019 WER, 0.010 CER, 0.96
numeric F1. **The open-source comparison on this page was not measured**: the
scanned fixture was not run through Part 1's Tesseract stage before the
deadline. It is the comparison that matters most for the decision, since a scan
is exactly where a managed service is supposed to be worth its price, and it is
the first thing to run next. The brief's acceptance (one page and one table
side by side) is met by the two statement pages above.

## 4. Fallback design

Textract is implemented as an optional fallback, following the tutorial's flow:
open-source parse first; if a page's OCR confidence or a table's score falls
below threshold, check the cache; on a miss, call the API only if
`managed.enabled` is true; otherwise keep the open-source result and flag the
page.

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

The call site is `managed_fallback()` in `src/tables.py` (Part 2's stage),
run for every page after the best table is chosen. It fires only when a page has
a real table, meaning at least `tables.min_numeric_rows` (3) rows with numbers,
and that table scores below `managed.trigger.min_table_score` (0.50). The rule
reuses Part 2's own setting rather than adding a new one.

The outcome of every check is recorded in a new `fallback` column at the end of
`data/tables/log/tables_log.csv`:

| Value | Meaning |
|---|---|
| empty | No check needed: no real table, or the table scored well |
| `used` | The managed answer was used, written to `data/tables/managed/<stem>_p<page>.blocks.jsonl` |
| `miss` | Nothing cached and `managed.enabled` is false, so the open-source result is kept |
| `error` | The check could not run (for example, no `pdftoppm`); the stage carries on |

The check never raises. A machine without `pdftoppm` or AWS credentials still
completes the tables stage, which is what keeps `dvc repro` working with the
fallback disabled. Part 2's own outputs are untouched: the full stage still
writes the same 32 tables with the same winning methods. `tests/test_managed_fallback.py`
covers the five cases: no table, an empty candidate, a good score, a cache miss,
and a check that fails.

The OCR-confidence side of the trigger, inside Part 1's parsing stage, is not
wired. On these two filings only the table side is exercised.

The cache is tracked with `dvc add data/managed` (`data/managed.dvc`).
`src/managed`, `data/managed` and the `managed` params are dependencies of the
`tables` stage, and `data/managed` of the `evaluate` stage, so a change to the
cache, the code or the switch reruns what reads them. `dvc repro -s tables`
with `managed.enabled: false` completes and writes the same 32 tables.

The team's S3 remote (`lantern-s3`) now exists, but `dvc push
data/managed.dvc` from this account returns 403 Forbidden: the bucket is in a
different AWS account from the one used for Textract. Until the cache is
pushed, a fresh clone cannot `dvc pull` it, and because `tables` depends on
`data/managed`, `dvc repro` there stops at that stage. Pushing it is pending
with the Part 8 owner.

One known false trigger to fix before wiring the OCR side: 10-Q p7 is blank and
wrongly routes to OCR in Part 1. An OCR-confidence trigger built on that routing
would pay Textract to read a blank page.

### A false trigger the table side had, and how it was found

The first version fired when any table candidate scored below 0.50. Run on both
filings, it fired on **45 of 91 pages**. Every one of them scored exactly 0.0
with no numeric rows: prose pages, signature pages and the like, where Camelot's
stream mode returns an empty candidate. Those are pages with no table, not pages
with a badly read table, and a managed service has nothing to fix on them.
Enabled, that rule would have sent half of every filing to Textract. Requiring
three numeric rows removed all 45, and a regression test now guards the case.

## 5. Pricing

From the AWS Textract pricing page, checked 8 October 2026
(https://aws.amazon.com/textract/pricing/):

| Meter | First 1M pages / month | After 1M |
|---|---|---|
| `AnalyzeDocument`, Tables (OCR included) | $15.00 per 1,000 | $10.00 per 1,000 |
| `AnalyzeDocument`, Layout with Tables | included, no charge | included |
| `DetectDocumentText` (OCR only, no tables) | $1.50 per 1,000 | $0.60 per 1,000 |

Our call uses Tables plus Layout, which AWS bills as Tables alone: **$0.015 per
page**. AWS's worked examples are priced for US West (Oregon); we ran in
us-east-1, so confirm the regional figure in the AWS Pricing Calculator before
quoting it to a client.

Free tier: three months for new customers, including 100 pages a month of
`AnalyzeDocument` with Tables and Layout.

**Measured spend for this part:** three pages, so $0.045 at list price, and
nothing if the account is still in its free tier window.

> TO FILL: Cost Explorer figure for Amazon Textract, October 2026, and the date
> it was checked (Cost Explorer lags by several hours).

## 6. Cost at FinTrust's volume

Assumptions, each stated so it can be replaced:

- 5,000 filings a year at about 100 pages each, the tutorial's planning figure:
  **500,000 pages a year**, about 41,700 a month, all inside the first price
  tier. Our two filings average 45.5 pages (61 and 30), so this is a
  conservative upper bound.
- Self-hosted compute: $0.17 per 1,000 pages, the tutorial's anchor (a $0.40/h
  VM at 1.5 s per page), excluding engineering time. Part 10's measured figure
  in `reports/benchmarks.md` replaces this when merged.
- Engineering time: $100 per hour, fully loaded. An assumption, not a
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
engineer-hours a year, about an hour and a half a week**.

So the crossover for FinTrust is stated in maintenance time, not pages: if
keeping the open-source parsers working costs more than about 74 hours a year,
Textract on everything is cheaper; if it costs less, building is cheaper. In
general, managed wins when yearly maintenance cost exceeds
`pages per year x (managed price - self-hosted price)`.

The hybrid makes that question mostly disappear. Routing only failing pages to
Textract keeps the managed bill in the tens to hundreds of dollars, while the
open-source path, which reads born-digital pages exactly, handles everything
else.

**Measured trigger rate on our two filings: 0 of 91 pages.** No page has a real
table scoring below 0.50, so on clean born-digital filings like Apple's the
table fallback costs nothing at all. The 5% and 1% rows above are therefore
scenarios for harder documents (other issuers, older filings, scans), not
measurements; the measured figure for this corpus is 0%.

## 7. Data handling

From the AWS Textract FAQ, Data Privacy section, checked 8 October 2026
(https://aws.amazon.com/textract/faqs/):

- **Training use.** By default AWS may store and use document inputs to provide
  the service and to improve Textract and other Amazon AI technologies. Opting
  out requires an AWS Organizations AI services opt-out policy; it is an
  account-level setting, not a per-request flag.
- **Region.** Content is encrypted and stored at rest in the region where
  Textract is called, but unless the opt-out is in place, some content may be
  stored in another region for service improvement. Region pinning therefore
  depends on the opt-out.
- **Retention.** The FAQ gives no fixed retention period. Deletion of stored
  inputs is by request to AWS Support.
- **Ownership and compliance.** The customer keeps ownership of content.
  Textract is HIPAA eligible, in scope for PCI, ISO and SOC, and can be called
  through a VPC endpoint so requests avoid the public internet.

Questions that must be answered before any client document goes through this
path:

1. Is the AI services opt-out policy applied to the AWS Organization that owns
   the account? The account used here is a course account under an IAM user;
   whether an opt-out exists on it was not checked.
2. Which region must client data stay in, and is that region guaranteed only
   with the opt-out in place?
3. What retention does the client's contract require, given that AWS deletes on
   request rather than on a schedule?
4. Does the client's data agreement permit a third-party processor at all?

For this project the risk is low: public SEC filings, already published on
EDGAR. The same pipeline pointed at client documents would not be low risk, and
the `managed.enabled` flag should stay off for them until those four answers
exist.

## 8. Recommendation

Do not use Textract for everything. Use it as a fallback, on a narrow set of
pages, behind the flag.

**Where it belongs:** scanned pages and pages that fail the OCR or table
trigger. That is where it measurably outperforms, and where the open-source
path has no text layer to read.

**Where it does not:** born-digital filings, which is nearly all of FinTrust's
volume. There the text layer is exact, the open-source paths read statement
figures within about one to four points of Textract (Docling within one point
on p6, and it reads the clipped parentheses that the traditional path loses),
and Textract adds OCR errors the text layer never had.

**Lina's question, "Why not just use Textract for everything?", in five
sentences.** On accuracy, the gap on digital statement pages is about one to
four points of numeric F1, Docling already fixes the one reading error Textract
fixed, and Textract introduces errors there by OCRing text the PDF already
holds exactly. On cost, Textract on every page is about $7,500 a
year at FinTrust's volume against under $100 of compute, so it only wins if
maintaining our parsers costs more than about 74 engineer-hours a year. On
lock-in, its output is a provider-specific block graph that still needs mapping,
scale normalisation and section context, so buying it does not remove the
engineering, it moves it. On data handling, client documents would need an
account-level training opt-out, a region guarantee and a retention answer
before a single page is sent. So we keep the open-source path as the default
and send only scans and failing pages to Textract, which is cheaper, more
accurate where it matters, and keeps client data at home unless we choose
otherwise.

## 9. Limitations

- Three pages, two of them from one company's unusually clean filings. The
  statement-page comparison is strong evidence for clean digital tables and
  weak evidence for anything else.
- The scanned-page comparison against Tesseract was not measured (section 3).
- The cache is not yet in the team's DVC remote (section 4).
- One provider only; Google Document AI and Azure were not run (stretch goal).
- The measured table trigger rate of 0 of 91 comes from one company's clean
  filings. The 5% and 1% fallback rates are scenarios for harder documents, not
  measurements (section 6).
- Only the table side of the trigger is wired. The OCR-confidence side in Part
  1 is not (section 4).
- Prices are list prices for the first tier; volume discounts and custom quotes
  are not considered.