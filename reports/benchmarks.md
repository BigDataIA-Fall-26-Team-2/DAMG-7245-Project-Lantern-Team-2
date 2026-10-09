# Part 10: EC2 CPU benchmarks and cost

## Evidence and status

This report uses the successful CPU measurements from the team's EC2 reproduction.
[ec2_benchmark_observed.csv](ec2_benchmark_observed.csv) is a transcription of the
benchmark summary printed in the EC2 terminal and supplied by Lokesh; it is not a
new execution or a downloaded copy of `data/bench/summary.csv`.

**Final verification pending:** after merging the device-handling fix, run
`dvc repro bench` on EC2, inspect `data/bench/summary.csv`, `cost.csv`, `machine.json`,
and `skipped.json`, and update this report to match that run before the final DVC
push. The measurements below describe the earlier successful CPU jobs, not the
pending corrected run. Mac/MPS performance comparisons are not used in this report.

## Hardware and method

The recorded reproduction environment is Ubuntu 24.04.4 LTS on an x86_64 EC2
m7i-flex.large instance, approximately 8 GiB RAM, Python 3.11 and CPU-only
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
| parse_pdfplumber | 94 | 0.114 | 0.505 | 0.315 | 29.6 | 0.27 | 632.4 | 0 | 1 |
| tables | 94 | 0.532 | 0.976 | 0.527 | 49.6 | 0.64 | 235.1 | 0 | 62 |
| layout | 94 | 0.748 | 2.284 | 1.021 | 96.0 | 3.45 | 1611.2 | 0 | 1 |
| parse_docling_cpu | 94 | 4.798 | 16.658 | 6.536 | 614.4 | 3.88 | 1624.7 | 0 | 3 |

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
`0.315 + 0.527 + 1.021 = 1.863 seconds/page`. Docling uses `6.536 seconds/page`.
For each measured path:

```text
hours/year = seconds/page × pages/year ÷ 3600 ÷ assumed workers
cost/year = hours/year × configured hourly price
managed cost/year = pages/year × configured per-page service price
```

These formulas are implemented in [bench.py](../src/bench.py). Final numeric cost
rows will be taken from the corrected EC2 `cost.csv` after the pending rerun.
Applying these timings to the configured c7i.2xlarge is a hardware extrapolation:
that instance type was not benchmarked here. Four-way scaling is unmeasured and
may be optimistic because each process can already use multiple CPU threads.
No GPU estimate is supported by this CPU-only run.

The measurement-host row excludes compute charges by construction; a zero in
that row must not be interpreted as free EC2 hosting. Storage, network, idle
instance time, engineering, and maintenance are outside this model.

## Bottlenecks and recommendation

Docling dominates the observed page-processing time: 614.4 seconds versus 96.0
for layout, 49.6 for tables, and 29.6 for text/OCR. Its p95 is 16.658 seconds/page.
Setup is smaller than total page time in each measured stage; retaining warm
workers can reduce repeated setup, but concurrency needs a separate measurement.

Use the demonstrated CPU configuration for this submission. The measurements do
not establish whether a GPU would improve performance or reduce cost. Keep DVC
caching for unchanged filings and selective OCR for pages that need it. Decide
between managed and local extraction using quality, maintenance effort, and the
explicit cost assumptions, not failed GPU timings. See [build_vs_buy.md](build_vs_buy.md)
for the managed-service quality comparison.

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
- The corrected EC2 rerun, final generated CSV comparison, and artifact upload are
  still pending; the transcription above preserves the supplied observations.
