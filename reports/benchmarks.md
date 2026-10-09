# Part 10: Benchmarks and cost

All numbers come from `python src/bench.py` (stage CSVs, `summary.csv`, `cost.csv` and `machine.json` in `data/bench/`)
or from the cited price pages. Prices and assumptions live in `params.yaml: bench`.

## Hardware and method

**Machine:** Apple M3 Pro, 11 cores (11 logical), 18 GB RAM, macOS 14.8.4, Python 3.11.16, PyTorch with MPS (Mac GPU)
available, no CUDA. LayoutParser runs on CPU. Docling is benchmarked twice, pinned with `docling.device`: `cpu` (comparable
to a CPU-only VM) and `mps` (the Mac GPU).

**Batch:** all 91 rendered Apple pages (10-K 61, 10-Q 30: cover, prose, statements, notes) plus the 3 image-only pages of
`tests/fixtures/scanned.pdf`, so OCR is measured (Apple pages never need it): **94 pages**.

**Method:** each stage runs in its own process, so peak memory isn't inflated by another stage's models. Model loading is
timed separately as setup (cold start). Per page: wall-clock seconds, process RSS, output count, and status (`ok`,
`empty` = no output, `error` = exception). Process RSS is used because PyTorch, Tesseract and OpenCV allocate outside Python.

Each benchmark times the **same per-page work as the real stage, including its outputs**: `parse_pdfplumber` extracts and
writes text and word boxes; `tables` calls `extract_best_df`, which includes `to_long` normalization; `layout` includes text
and table routing; `parse_docling` converts the page and then runs the stage's own export functions (Markdown, JSON,
blocks with converted boxes, raw tables and `to_long`-normalized tables). Outputs go to a scratch folder, not `data/`.
(After review on #107: an earlier conversion-only Docling timing understated it by 4% on CPU and 16% on MPS.)

## Results (94 pages)

| Stage | Device | s/page p50 | s/page p95 | s/page mean | Setup (cold) | Peak RSS (MB) | Errors | Empty | Notes |
|---|---|---|---|---|---|---|---|---|---|
| parse_pdfplumber | CPU | 0.051 | 0.235 | 0.114 | 0.16 s | 710 | 0 | 1 | OCR pages 1.2-2.7 s vs ~0.05 s native; peak RSS from OCR |
| tables | CPU | 0.234 | 0.440 | 0.235 | 0.25 s | 218 | 0 | 62 | empty = no table on the page |
| layout | CPU | 0.465 | 1.492 | 0.631 | 1.60 s | 1,960 | 0 | 1 | includes text + table routing |
| parse_docling | CPU | 0.925 | 3.428 | 1.332 | 2.26 s | 1,682 | 0 | 3 | p95 = table-heavy pages (TableFormer + normalization) |
| parse_docling | MPS | 0.730 | 3.533 | 1.092 | 2.33 s | 1,323* | 0 | 3 | 18% less total time than CPU |

\* GPU memory is not fully counted in process RSS, so the MPS peak is likely an underestimate.

**Failures:** 0 errors in every stage. Empty pages are expected: the blank 10-Q p7 is empty in all three of pdfplumber,
layout and Docling (pdfplumber spends extra time there because a 0-character page triggers its OCR fallback). Docling also
returns nothing for scanned p1 and p3 because `do_ocr: false`; on scanned p2 its layout model still detects regions,
without text.

**Cold vs warm:** model loading takes 1.6-2.3 s, small next to 59-125 s of per-page work per stage, so warm workers matter
for latency but not for batch cost.

## Cost (5,000 filings/year, ~100 pages each = 500,000 pages)

| Option | Hardware | s/page | Workers | Hours/year | $ / 1,000 pages | **$ / year** |
|---|---|---|---|---|---|---|
| Traditional (P1+P2+P3) | laptop M3 Pro | 0.980 | 1 | 136.1 | 0 | **0** |
| Docling | laptop M3 Pro (MPS) | 1.092 | 1 | 151.7 | 0 | **0** |
| Traditional (P1+P2+P3) | c7i.2xlarge (8 vCPU, 16 GiB) | 0.980 | 4 | 34.0 | 0.024 | **12.15** |
| Docling | c7i.2xlarge | 1.332 | 4 | 46.2 | 0.033 | **16.51** |
| Docling | g4dn.2xlarge (T4 GPU) | 1.092 | 1 | 151.7 | 0.228 | **114.05** |
| Textract OCR only | managed API | | | | 1.50 | **750** |
| Textract with tables | managed API | | | | 15.00 | **7,500** |

**Prices (on-demand, us-east-1):** c7i.2xlarge $0.357/h (doit.com/compute/spot/us-east-1/c7i.2xlarge), g4dn.2xlarge
$0.752/h (devzero.io/instances/aws/g4dn.2xlarge), Textract DetectDocumentText $0.0015/page and AnalyzeDocument Tables
$0.015/page for the first 1M pages a month, layout included free with Tables (aws.amazon.com/textract/pricing). The EC2 prices
come from price trackers; confirm in the AWS Pricing Calculator before budgeting.

**Assumptions:** traditional s/page = sum of the three stage means (all run on every page). 4 workers on an 8 vCPU / 16 GiB
VM (peak ~2 GB per worker) is an assumption, not measured; PyTorch already uses several cores per process, so real scaling
will be less than 4x. The cloud GPU row uses the Mac GPU timing as a proxy for a T4. VM per-core speed is assumed similar
to the M3 Pro. Engineering time, storage and data transfer are excluded. `cost.csv` only includes options whose stages
were benchmarked.

## Bottlenecks and recommendation

- **Bottlenecks:** Docling on table-heavy pages (p95 3.4 s CPU, 3.5 s MPS), then layout (p95 1.5 s, mostly table routing
  through Camelot). Text extraction is negligible except on OCR pages (25-50x slower), so OCR only pages that need it, as P1 does.
- **Hardware:** a CPU VM. The Mac GPU cut Docling's total time by only 18%, because exports and table normalization run on
  the CPU, while the cloud GPU costs ~2x per hour, so at this volume the GPU raises cost per page (~$0.23 vs ~$0.03 per
  1,000 pages). Revisit only if volume grows by orders of magnitude or latency matters.
- **Concurrency:** process-level workers, one model copy each (~2 GB), so about 4 per 16 GiB VM; keep workers warm to avoid
  the ~2 s model load per job. Cache outputs by document hash so reruns skip unchanged filings.
- **Download limit:** SEC EDGAR allows 10 requests/second. At an estimated few requests per filing (not measured), 5,000
  filings take well under an hour to fetch at full rate, so downloading is not the bottleneck; parsing is.
- **Build vs buy:** compute for either open-source path is ~$12-17 a year, against $7,500 for Textract with tables. Textract
  is only cheaper if it saves more than $7,500 a year of engineering and maintenance time; at FinTrust's volume, engineering
  hours, not compute, decide the choice.

## Limitations
- One run per stage on one machine; no repeated trials or variance.
- Peak RSS is sampled after each page, so short spikes inside a page can be missed.
- Docling per-page timing uses `page_range=(n, n)`, so each page pays a small per-call overhead.

## Reproducing on other hardware

The measurements above are the recorded Mac experiment, not fresh EC2 measurements.
The benchmark checks PyTorch device availability before launching MPS or CUDA runs.
Unavailable configured devices are recorded in `data/bench/skipped.json`; their stale
per-stage CSV/meta files are removed from the current output directory **only after
archiving**. Before any run overwrites files, all existing top-level CSV/JSON files
(including summary, costs, and machine metadata) are copied byte-for-byte to
`data/bench/history/<content-sha256>/`. This directory is included in the existing
DVC `data/bench` output. The printed archive path identifies the preserved run.

For the Mac results quoted above, use the archive whose `machine.json` identifies
Apple M3 Pro/macOS, and its `summary.csv`, `cost.csv`, and stage CSVs. A rerun can
only archive files actually present locally: if the original Mac evidence was
never transferred, obtain that original bundle from its author before claiming
these report numbers are reproduced. An EC2 archive is not evidence for the Mac
figures. Preserve that original bundle in its own `data/bench/history/` folder
with its machine metadata before the final DVC push.

`summary.csv` summarizes only stages requested in the current run. Page failures
remain visible as error counts, but any stage with errors or no measured pages is
excluded from `cost.csv`. An all-skipped subset produces an empty summary and only
the configured managed-service price scenarios. Local-host zero-cost rows exclude
compute charges; they do not assert that running an EC2 instance is free. VM rows
remain projections using the configured prices and worker assumptions, not direct
measurements on the named VM types.
