# Shravya AI Engineering Log

## P4 Docling conversion and comparison

- Tool: Claude (Anthropic), claude.ai chat. Drafted `src/docling_parse.py` (exports, blocks, table export through `tables.to_long`, HTML conversion), the comparison scripts and `reports/docling_comparison.md`.
- Verification: before/after `pip freeze` diff when installing Docling showed two downgrades (`huggingface_hub` 2.1.1 -> 1.33.0, `websockets` 17.2 -> 16.1.1). I read every installed package's version limits to find the cause (`docling-slim`, `docling-ibm-models` and `tokenizers` need `huggingface_hub<2`; `docling-slim` needs `websockets<17`), then re-ran P3 layout detection on 10-K page 10 to confirm it still gives 7 Text blocks on the older version before changing the P3 pin. Checked converted Docling boxes against pdfplumber word positions on the multicolumn fixture (now within ~1.5 pt), and confirmed the cropbox offset is zero on every Apple page. Compared 243 statement-table cells across 4 pages against the traditional path (0 differences) and confirmed the 10-K balance sheet totals balance (359,241).
- Changes: the case study requires the file name `docling_parse.py`, which is also Docling's own parser package, so running the script made Docling import it (circular import). The script now removes `src/` from `sys.path`, pre-loads Docling's real package, then re-adds `src/` to import `tables`. Docling boxes were off by (15.5, 63.9) pt on the rotated, cropped fixture because Docling measures from the cropbox; added a per-rotation cropbox offset. Docling tables reuse `tables.to_long` with the full page text, so scaling and period labels match the traditional path and Dhruvi's `xbrl.py` needs no flag change.
- Limitation: AI-written commands were wrong three times and I caught each one: a dry-run check that can't detect dependency conflicts, a `\n` that broke a file-editing script (the crash happened before any write, so nothing changed), and a backslash inside an f-string that Python 3.11 rejects. The recommendation in `docling_comparison.md` is provisional until P9/P11 metrics exist; statement agreement partly reflects shared post-processing.
- Confidence: high for the conversion, box normalization and table comparison; the final recommendation depends on teammates' metrics. I can explain, modify, test and defend every part of this work.
## P3 environment setup

- Tool: Claude (Anthropic), claude.ai chat. Suggested building the team `.venv` from an existing conda Python 3.11 (which already provides Tesseract and Poppler) instead of Homebrew, which compiles from source on macOS 14.
- Verification: `pip check` clean; README import check printed `Imports OK`; Tesseract 5.5.2 and Poppler 26.09.0 match the versions verified in the README. Before/after `pip freeze` diff when adding LayoutParser showed 17 packages added and none changed.
- Changes: `pikepdf==10.16.0` has no macOS 14 wheel and fails to build (missing qpdf headers), so I installed a pre-built pikepdf 10.13 locally and installed the rest from a copy of `requirements.txt` without that pin. The team file was not changed for this.
- Limitation: `opencv-python` (LayoutParser) and `opencv-python-headless` (Camelot) are both installed. They are the same version and `cv2`, `camelot` and `layoutparser` import together, but two OpenCV packages sharing one folder is fragile. Verified on macOS 14 arm64 only.
- Confidence: high for the local setup; Linux clean-room install unverified.

## P3 layout model loading

- Tool: Claude. Diagnosed why `AutoLayoutModel` failed: LayoutParser's built-in Dropbox link returns a ~205 kB web page instead of the ~45 MB weights. Suggested the LayoutParser team's Hugging Face repo and drafted `load_model()` with an automatic download.
- Verification: downloaded file is 45 MB; the model loads and reports the PubLayNet label map {1: Text, 2: Title, 3: List, 4: Table, 5: Figure}.
- Changes: PyTorch 2.6 refuses the checkpoint in weights-only mode because it also stores training args and numpy types. Instead of `weights_only=False`, I allowlisted exactly the types PyTorch named (`argparse.Namespace`, numpy scalar and dtype classes), adding them one at a time as each error reported the next. Replaced `lp.draw_box`, which breaks on current Pillow (`getsize` removed), with a small PIL drawing function.
- Limitation: depends on the Hugging Face URL staying up; `models/` is gitignored.
- Confidence: high.

## P3 detection, threshold and post-processing

- Tool: Claude. Drafted `detect_page`, duplicate removal, reading order, text routing with OCR fallback, sections, the footer filter, and the threshold and padding sweep scripts.
- Verification: I ran the threshold sweep on 9 mixed pages and chose 0.25 from the results (0.25/0.2/0.1 identical; 0.4 and 0.5 left 10-Q page 2 with no blocks). I ran the padding sweep and chose 8 pt (clipped starts 132 -> 35 on the 10-K), then spot-checked the 15 remaining cases by hand. Confirmed 10-Q page 7 is genuinely blank (0 characters, empty at threshold 0, checked visually). Checked reading order and text on 10-K page 10 against the page.
- Changes: overlaps removed by score kept the wrong box on 10-K page 10 (a straddling box beat the correct paragraph box), so I documented it as a detector limitation rather than tuning further. The section names were being taken from the page footer; I checked for running headers by counting repeated Title texts (none repeat on most pages) and added a footer-only filter. Added `pages.csv` so blank pages are recorded instead of faking a block.
- Limitation: AI estimates were wrong twice and I caught both: it expected ~60 footers (actual 9), and the practice "multi-column" fixture it picked turned out to be single-column, because its detection heuristic counted words on both page halves, which any full-width paragraph satisfies.
- Confidence: high for the code and measurements; layout quality itself is limited by the model (see audit).

## P3 detector audit and report

- Tool: Claude. Proposed the audit categories (correct / missed / wrong type / bad box), helped read overlays, and drafted `reports/layout_audit.md`.
- Verification: I opened all 10 overlay images and checked every count against the page; the summary script's totals (Text 21/55, Title 13/33, Table 1/32) match the per-page counts.
- Changes: added the "bad box" category, since box-extent errors were the most common failure and leaving them out would overstate quality. Excluded page footers from the counts and reported them separately.
- Limitation: counts are one person's judgement; block boundaries (e.g. grouping cover-page fields) involve calls another reviewer might make differently.
- Confidence: high that the failure patterns are real (tables boxed as numbers only, repurchase tables labeled Figure); moderate on exact counts. I can explain, modify, test and defend every part of this work.

## P10 Benchmarks and cost

- Tool: Claude (Anthropic), claude.ai chat. Drafted `src/bench.py` (one subprocess per stage, per-page timing, RSS and status, summary and cost tables), the `docling.device` setting, and `reports/benchmarks.md`; looked up Textract and EC2 prices.
- Verification: quick runs on 1-2 pages per PDF before the full 94-page run; 0 errors in every stage. Checked which pages were empty in the stage CSVs instead of assuming, and confirmed the blank 10-Q p7 is empty in all three stages. Confirmed Docling works on both devices (statement page, warm: CPU 2.75 s, MPS 2.10 s) and the full suite still passes (53). Textract prices taken from AWS's own pricing page; EC2 prices from price trackers, flagged in the report to confirm in the AWS Pricing Calculator.
- Changes: measured on my own machine (Apple M3 Pro, 11 cores, 18 GB). Each stage runs in its own process so one stage's models don't inflate another's peak memory. Added the scanned fixture to the batch so OCR cost is measured, since Apple pages never need OCR. Added `docling.device` (auto/cpu/mps) so Docling's CPU and GPU timings are measured separately rather than mixed.
- Limitation: AI claims I corrected: it first said my Mac had no GPU for these models (MPS is available and Docling uses it on `auto`), and it guessed Docling's 3 empty pages were the 3 scanned pages (actually the blank 10-Q p7 plus scanned p1 and p3; scanned p2 had layout regions). Worker count per VM and the Mac-GPU-as-T4 proxy are stated assumptions, not measurements; one run per stage, no variance.
- Confidence: high for the measured per-stage timings and memory on this machine; moderate for the cloud cost estimates, which depend on the stated assumptions. I can explain, modify, rerun and defend every part of this work.

## P4 stretch: docling-serve over HTTP (#83)

- Tool: Claude (Anthropic), claude.ai chat. Suggested running docling-serve as a pinned Docker container (so no packages go into requirements.txt), drafted `convert_via_serve()`, the `serve_url` switch, the tests and the report section.
- Verification: listed the server's endpoints from its own openapi.json and read /version instead of assuming them; converted the statement fixture by hand first; then ran the real stage through the server on both filings and compared with the library: same table and block counts, same HTML conversion, `diff -rq` shows all 54 team-format CSVs identical. Full suite 95 passed.
- Changes: `serve_url` defaults to empty, so the library path and every teammate's run are unchanged; the image is pinned by digest, not `latest`; a failed conversion raises instead of writing outputs; tests use a fake `requests.post`, so they run in CI without Docker.
- Limitation: the server runs Docling 2.132.0 vs the library's 2.134.0 (same models); raw table headers join levels with "." instead of " - ", which does not reach the team-format tables. Server was ~1.8x slower on my Mac (Docker VM, CPU only); not measured on Linux.
- Confidence: high that the HTTP path produces the same outputs on these filings. I can explain, modify, rerun and defend this work.
