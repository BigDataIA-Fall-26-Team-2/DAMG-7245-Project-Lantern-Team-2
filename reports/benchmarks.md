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
Each stage does the same per-page work as the real stage (layout includes text and table routing).

## Results (94 pages)

| Stage | Device | s/page p50 | s/page p95 | s/page mean | Setup (cold) | Peak RSS (MB) | Errors | Empty | Notes |
|---|---|---|---|---|---|---|---|---|---|
| parse_pdfplumber | CPU | 0.049 | 0.221 | 0.117 | 0.16 s | 718 | 0 | 1 | OCR pages 1.2-2.7 s vs ~0.05 s native; peak RSS from OCR |
| tables | CPU | 0.234 | 0.440 | 0.235 | 0.25 s | 218 | 0 | 62 | empty = no table on the page |
| layout | CPU | 0.465 | 1.492 | 0.631 | 1.60 s | 1,960 | 0 | 1 | includes text + table routing |
| parse_docling | CPU | 0.841 | 3.800 | 1.278 | 2.38 s | 1,708 | 0 | 3 | p95 = table-heavy pages (TableFormer) |
| parse_docling | MPS | 0.626 | 3.094 | 0.945 | 2.60 s | 1,300* | 0 | 3 | 26% less total time than CPU |

\* GPU memory is not fully counted in process RSS, so the MPS peak is likely an underestimate.

**Failures:** 0 errors in every stage. Empty pages are expected: the blank 10-Q p7 is empty in all three of pdfplumber,
layout and Docling (pdfplumber spends 0.78 s there because a 0-character page triggers its OCR fallback). Docling also
returns nothing for scanned p1 and p3 because `do_ocr: false`; on scanned p2 its layout model still detects regions,
without text.

**Cold vs warm:** model loading takes 1.6-2.6 s, small next to 59-120 s of per-page work per stage, so warm workers matter
for latency but not for batch cost.

## Cost (5,000 filings/year, ~100 pages each = 500,000 pages)

| Option | Hardware | s/page | Workers | Hours/year | $ / 1,000 pages | **$ / year** |
|---|---|---|---|---|---|---|
| Traditional (P1+P2+P3) | laptop M3 Pro | 0.983 | 1 | 136.5 | 0 | **0** |
| Docling | laptop M3 Pro (MPS) | 0.945 | 1 | 131.2 | 0 | **0** |
| Traditional (P1+P2+P3) | c7i.2xlarge (8 vCPU, 16 GiB) | 0.983 | 4 | 34.1 | 0.024 | **12.19** |
| Docling | c7i.2xlarge | 1.278 | 4 | 44.4 | 0.032 | **15.84** |
| Docling | g4dn.2xlarge (T4 GPU) | 0.945 | 1 | 131.2 | 0.197 | **98.70** |
| Textract OCR only | managed API | | | | 1.50 | **750** |
| Textract with tables | managed API | | | | 15.00 | **7,500** |

**Prices (on-demand, us-east-1):** c7i.2xlarge $0.357/h (doit.com/compute/spot/us-east-1/c7i.2xlarge), g4dn.2xlarge
$0.752/h (devzero.io/instances/aws/g4dn.2xlarge), Textract DetectDocumentText $0.0015/page and AnalyzeDocument Tables
$0.015/page for the first 1M pages a month, layout included free with Tables (aws.amazon.com/textract/pricing). The EC2 prices
come from price trackers; confirm in the AWS Pricing Calculator before budgeting.

**Assumptions:** traditional s/page = sum of the three stage means (all run on every page). 4 workers on an 8 vCPU / 16 GiB
VM (peak ~2 GB per worker) is an assumption, not measured; PyTorch already uses several cores per process, so real scaling
will be less than 4x. The cloud GPU row uses the Mac GPU timing as a proxy for a T4. VM per-core speed is assumed similar
to the M3 Pro. Engineering time, storage and data transfer are excluded.

## Bottlenecks and recommendation

- **Bottlenecks:** Docling on table-heavy pages (p95 3.8 s CPU), then layout (p95 1.5 s, mostly table routing through
  Camelot). Text extraction is negligible except on OCR pages (25-50x slower), so OCR only pages that need it, as P1 does.
- **Hardware:** a CPU VM. The Mac GPU cut Docling's time by only 26%, while the cloud GPU costs ~2x per hour, so at this
  volume the GPU raises cost per page (~$0.20 vs ~$0.03 per 1,000 pages). Revisit only if volume grows by orders of magnitude
  or latency matters.
- **Concurrency:** process-level workers, one model copy each (~2 GB), so about 4 per 16 GiB VM; keep workers warm to avoid
  the 2 s model load per job. Cache outputs by document hash so reruns skip unchanged filings.
- **Download limit:** SEC EDGAR allows 10 requests/second. At an estimated few requests per filing (not measured), 5,000 filings take well under an
  hour to fetch at full rate, so downloading is not the bottleneck; parsing is.
- **Build vs buy:** compute for either open-source path is ~$12-16 a year, against $7,500 for Textract with tables. Textract
  is only cheaper if it saves more than $7,500 a year of engineering and maintenance time; at FinTrust's volume, engineering
  hours, not compute, decide the choice.

## Limitations
- One run per stage on one machine; no repeated trials or variance.
- Peak RSS is sampled after each page, so short spikes inside a page can be missed.
- Docling per-page timing uses `page_range=(n, n)`, so each page pays a small per-call overhead; whole-filing conversion
  ran at ~0.9-1.2 s/page.
