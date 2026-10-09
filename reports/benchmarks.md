# Part 10: EC2 CPU benchmarks and cost

## Evidence and status

This report uses the final corrected CPU benchmark artifacts retrieved from the
team's EC2 deployment checkout on October 9, 2026.
[ec2_benchmark_observed.csv](ec2_benchmark_observed.csv) copies the values from
`data/bench/summary.csv` (line endings normalized), downloaded from `/home/ubuntu/lantern-streamlit`.
The accompanying `cost.csv`, `machine.json`, and `skipped.json` were retrieved
from the same output folder. No benchmark was rerun for this report update.
The final reproduction log records the DVC artifact upload to S3; this update
verified the EC2 files directly, not a fresh S3 download.

## Hardware and method

The recorded reproduction environment is Ubuntu 24.04.4 LTS on an x86_64 EC2
m7i-flex.large instance, 7.6 GiB reported RAM, 2 logical CPUs, Python 3.11.17 and CPU-only
PyTorch 2.14.1+cpu. Environment setup is recorded in
[Lokesh's engineering log](../docs/ai_log/lokesh.md); retain the final run's
`data/bench/machine.json` alongside its CSVs for machine-level provenance.

The workload is 94 pages per stage: 61 rendered Apple 10-K pages, 30 rendered
10-Q pages, and the three-page scanned fixture. Input selection and device options
are in [params.yaml](../params.yaml), under `bench`.

Each stage runs in its own subprocess. Setup/model loading is timed separately.
Per-page records contain elapsed seconds, process RSS, output count, and status.
Text extraction writes text and word boxes; tables include normalization; layout
includes text/table routing; Docling includes conversion and its export functions.
These per-page benchmarks are not a measurement of the entire DVC pipeline.

## Observed CPU results

Every row below maps to the same-named stage in
[ec2_benchmark_observed.csv](ec2_benchmark_observed.csv).
RSS values are labeled MB by the script but are calculated as bytes divided by 2^20 (MiB).

| Stage | Pages | p50 s/page | p95 s/page | Mean s/page | Total page time (s) | Setup (s) | Peak RSS (MiB) | Errors | Empty |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| parse_pdfplumber | 94 | 0.113 | 0.531 | 0.293 | 27.6 | 0.27 | 632.6 | 0 | 1 |
| tables | 94 | 0.542 | 0.994 | 0.54 | 50.8 | 0.64 | 234.9 | 0 | 62 |
| layout | 94 | 0.741 | 2.268 | 1.021 | 96.0 | 3.45 | 1617.3 | 0 | 1 |
| parse_docling_cpu | 94 | 4.78 | 16.48 | 6.503 | 611.3 | 3.88 | 1598.1 | 0 | 3 |

All CPU jobs completed without page errors. `empty` means no extracted output;
it is distinct from an exception and does not alone establish whether a page was
correctly processed. Empty outputs need interpretation against the source and
evaluation evidence in [eval.md](eval.md).

The earlier EC2 attempt also ran MPS despite its being unavailable. Those failure
timings are excluded here. The corrected benchmark records unsupported devices as
skipped, and excludes any stage with errors or no measured pages from cost estimates.

## Cost model

The scenario inputs are in `params.yaml: bench`: 500,000 pages/year, four assumed
workers, a named CPU VM price of $0.357/hour, and Textract OCR/table rates of
$0.0015/$0.015 per page. These are configured modeling assumptions, not a fresh
price quote or an EC2 billing measurement. The configured sources are
[CPU price reference](https://doit.com/compute/spot/us-east-1/c7i.2xlarge) and
[AWS Textract pricing](https://aws.amazon.com/textract/pricing/).

The traditional mean is the sum of the text, tables, and layout CSV means:
`0.293 + 0.540 + 1.021 = 1.854 seconds/page`. Docling uses `6.503 seconds/page`.
For each measured path:

```text
hours/year = seconds/page × pages/year ÷ 3600 ÷ assumed workers
cost/year = hours/year × configured hourly price
managed cost/year = pages/year × configured per-page service price
```

These formulas are implemented in [bench.py](../src/bench.py). The downloaded
final `cost.csv` reports the following projections:

| Option | Hardware assumption | USD / 1,000 pages | USD / year |
|---|---|---:|---:|
| Traditional (P1+P2+P3) | c7i.2xlarge, 4 workers | 0.046 | 22.98 |
| Docling | c7i.2xlarge, 4 workers | 0.1612 | 80.61 |
| Textract OCR | Managed API | 1.5 | 750.00 |
| Textract tables | Managed API | 15.0 | 7,500.00 |

Applying these timings to the configured c7i.2xlarge is a hardware extrapolation:
that instance type was not benchmarked here. Four-way scaling is unmeasured and
may be optimistic because each process can already use multiple CPU threads.
No GPU estimate is supported by this CPU-only run.

The measurement-host row excludes compute charges by construction; a zero in
that row must not be interpreted as free EC2 hosting. Storage, network, idle
instance time, engineering, and maintenance are outside this model.

## Bottlenecks and recommendation

Docling dominates the observed page-processing time: 611.3 seconds versus 96.0
for layout, 50.8 for tables, and 27.6 for text/OCR. Its p95 is 16.48 seconds/page.
Setup is smaller than total page time in each measured stage; retaining warm
workers can reduce repeated setup, but concurrency needs a separate measurement.

Use the demonstrated CPU configuration for this submission. The measurements do
not establish whether a GPU would improve performance or reduce cost. Keep DVC
caching for unchanged filings and selective OCR for pages that need it. Decide
between managed and local extraction using quality, maintenance effort, and the
explicit cost assumptions, not failed GPU timings. See [build_vs_buy.md](build_vs_buy.md)
for the managed-service quality comparison.

**Download limit (EDGAR).** SEC EDGAR allows at most 10 requests per second per user, across all clients/machines ([SEC policy](https://www.sec.gov/about/privacy-information)), and requires a
declared User-Agent (set in `params.yaml: download`). Downloading is therefore rate-limited, not compute-limited:
at an estimated 2 to 3 requests per filing (index plus full submission; not measured), 5,000 filings need about
10,000 to 15,000 requests, or roughly 17 to 25 minutes at the full rate. Parsing is the real bottleneck: at the
measured 6.503 s/page for Docling, 500,000 pages need about 226 hours with 4 workers. So download with a single
throttled client (at or below 10 requests/second, with retries on HTTP 429), and spend concurrency on parsing.

## Reproduction and evidence preservation

```bash
dvc repro bench
cat data/bench/skipped.json
cat data/bench/summary.csv
cat data/bench/cost.csv
```

Before replacing current outputs, the benchmark copies existing top-level CSV and
JSON files to `data/bench/history/<content-sha256>/`, preserving prior machine
metadata and raw measurements. That history is inside the DVC-managed output.
Current summaries include only requested, available stages. Historical files do
not feed the current cost calculations. An all-skipped run produces an empty
summary and only configured managed-service price scenarios.

Historical Mac files may be retained if available, but this EC2-only report does
not rely on them. Never relabel an EC2 archive as Mac evidence.

## Limitations

- One observed run on one host; repeated-trial variability was not measured.
- RSS is sampled after pages, so brief memory spikes can be missed.
- Docling converts individual page ranges, which adds per-call overhead.
- Full pipeline success and passing tests do not validate cost-model assumptions.
- The final EC2 files were retrieved and compared for this update. Fresh-cache
  S3 retrieval was not verified locally: the local AWS identity returned 403.
