# DAMG-7245-Project-Lantern-Team-2

Case Study 1 (DAMG 7245, Fall 2026): a reproducible pipeline that turns raw SEC 10-K/10-Q filings into a layout-aware, XBRL-validated corpus, versioned end-to-end with DVC.

- Team workflow and review process: [CONTRIBUTING.md](CONTRIBUTING.md)
- Part-by-part ownership and milestones: [WORKPLAN.md](WORKPLAN.md)
- AI-assistant rules for this repo (tool-agnostic — Claude, Codex, etc.): [SKILLS.md](SKILLS.md)

Full project summary, architecture diagram, reproduction steps, and the Codelab/demo links go here once the pipeline exists (required before submission, per Case Study 1 Section 8.2).

## Tools in use

| Tool | Used for | Pinned in |
|---|---|---|
| sec-edgar-downloader | P0: SEC filing downloads | requirements.txt |
| Playwright | P0: Chromium HTML-to-PDF rendering | requirements.txt |
| PyYAML | Pipeline parameter loading | requirements.txt |
| pypdf | PDF metadata and fixture inspection | requirements.txt |
| pdfplumber | P1: text and word boxes | requirements.txt |
| pytesseract | P1: Tesseract OCR wrapper | requirements.txt |
| pdf2image | P0/P1: Poppler rasterization | requirements.txt |
| img2pdf | P0: image-only scanned fixtures | requirements.txt |
| DVC + dvc-s3 | P8: pipeline and S3 remote support | requirements.txt |
| pytest | P8: smoke and regression checks | requirements.txt |
| GitHub Actions (checkout/setup-python) | P8: fixture-only PR smoke workflow | Commit SHAs in .github/workflows/smoke.yml |
| Camelot (camelot-py) + OpenCV (opencv-python-headless) | P2: table bake-off (lattice/stream/network/hybrid) and hybrid extractor | requirements.txt |
| pandas | P2/P11: table CSVs and XBRL value comparison | requirements.txt |
| Arelle (arelle-release) | P11: iXBRL fact extraction | requirements.txt |
| difflib | P11: fuzzy label-to-concept matching | Python standard library |
| Streamlit | App: team UI (frontend/) | requirements.txt |
| Docling | P4: alternative parsing path (layout, reading order, tables in one pass) | requirements.txt |
| docling-ibm-models (TableFormer) | P4: Docling's layout and table-structure models | requirements.txt |
| LayoutParser | P3: page layout detection (Text/Title/List/Table/Figure blocks) | requirements.txt |
| effdet (EfficientDet) | P3: PubLayNet detection backend for LayoutParser | requirements.txt |
| PyTorch + torchvision | P3: deep-learning runtime for the layout model | requirements.txt |
| huggingface_hub | P3: model weights host (LayoutParser's built-in link is dead) | requirements.txt |
<!-- Add one row per new tool/library the moment you introduce it (see SKILLS.md). -->

## Shared development environment

Use Python 3.11 explicitly: the default `python3` on the verified Mac is 3.14.
Install Python 3.11, Tesseract (English language data), and Poppler first. On
macOS: `brew install python@3.11 tesseract poppler`. On Linux, install the
Python 3.11 interpreter and venv support plus `tesseract-ocr`,
`tesseract-ocr-eng`, and `poppler-utils` with the distribution package manager.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python -c "import sec_edgar_downloader, yaml, pypdf, pdfplumber, pytesseract, pdf2image, img2pdf, dvc, dvc_s3, pytest; from playwright.sync_api import sync_playwright; print('Imports OK')"
python -c "import camelot, cv2, pandas, streamlit, difflib; from camelot.parsers import Lattice, Stream, Network, Hybrid; from arelle import Cntlr; print('Table, XBRL and app imports OK')"
tesseract --version
pdftoppm -v
dvc --version
```

On Linux, Playwright may also require `python -m playwright install-deps chromium`.
All teammates install from the root `requirements.txt` and add new pinned dependencies there. Activate `.venv`
in every new terminal; virtual environments are local and are not committed.
Ghostscript is not needed by this P0/P1/P8 toolset; the table owner should add it
only if the selected table extractor requires it.

Verified locally on macOS arm64 with Python 3.11.11, Tesseract 5.5.2, and
Poppler 26.09.0: dependency consistency, all listed imports, existing
`download`/`render`/`contracts` module imports from PR #88, and an offline
Chromium -> PDF -> pdfplumber -> Poppler -> Tesseract -> img2pdf smoke check.
The synthetic text `LANTERN 12345` survived both text extraction and OCR.
DVC 3.67.1 and pytest 9.1.1 start successfully.

Those checks verified the local prerequisite environment. The repository now
includes download/render scripts, text/OCR extraction, and regression tests.
The initial DVC pipeline is described below; S3 access and clean Linux
reproduction remain separate work.

Table, XBRL and app tools (issue #12): `camelot-py`, `opencv-python-headless`,
`pandas`, `arelle-release` and `streamlit` were added to the root
`requirements.txt` (35 new pins including dependencies). A
`pip install --dry-run` was run first and confirmed that no existing pin
changes. Verified locally on macOS arm64 with Python 3.11.17, Tesseract 5.5.3,
Poppler 26.09.0 and Ghostscript 10.08.0: `pip check` reports no broken
requirements, and camelot (Lattice/Stream/Network/Hybrid parsers), cv2,
pdfplumber, pandas, streamlit, arelle and difflib all import. These are import
checks only: table extraction quality is measured in the P2 bake-off (#17),
which will also confirm whether this Camelot version needs Ghostscript.

## P1: text and OCR

```bash
python src/parse_text.py --params params.yaml --input data/rendered --output data/parsed
python src/parse_text.py --params params.yaml --input tests/fixtures --output /tmp/lantern-parsed-fixtures
```

pdfplumber reads native text and word boxes page by page. A page uses Tesseract
when its non-whitespace character count is below `ocr.min_chars` **or** its
fraction of tokens containing `(cid:NN)` or the replacement character exceeds
`ocr.junk_ratio`. Tesseract reads a Poppler raster at `ocr.dpi` in `ocr.language`.
OCR supplies both text and boxes; pdfplumber does not perform OCR.

Outputs are `{stem}_p{NNNN}.txt`, `{stem}.words.jsonl` (one record per word), and
`ocr_log.csv` (one decision per page). Word records carry `doc_id`, `page`, `text`,
`bbox`, `ocr`, and `ocr_conf`. Pages are 1-based; boxes are top-left PDF points
in displayed page orientation, including rotation. Pixel boxes are scaled using
the actual raster dimensions. Confidence is Tesseract's 0–100 score, not a
calibrated probability; native words have null confidence. `doc_id` comes from
the input manifest; fixture directories without a manifest use null IDs and are
identified by stem in the log. The log records both trigger signals, reason,
engine, mean word confidence, and output text length, including empty pages.

Outputs are staged before replacement so an extraction error leaves the previous
run intact. Use a dedicated output directory for each input corpus: after a
successful run,
stale page-text and word-box files are removed, including those for PDFs no
longer in the input. Other files are retained. The log covers the current run.
Multi-column ordering and table structure remain P3/P2 work.

## P8: GitHub Actions smoke checks (issue #36)

`.github/workflows/smoke.yml` runs on every pull request, as required by
Case Study 1, Part 8 requirement 4 (page 11). The Ubuntu 24.04 job uses Python 3.11, Tesseract (English), and
Poppler. It extracts text and tables from `tests/fixtures/`, then runs the existing
pytest suite.
Outputs go to the runner's temporary directory.

`requirements-ci.txt` selects only the packages needed for these checks and uses
`requirements.txt` as a constraints file, keeping version pins in one place.
Pydantic supports the export/schema tests. Docling and layout load their model
packages only when conversion/detection is requested, so their existing helper
tests do not require model installations. The download/render packages are included for existing mocked tests; CI does
not download filings, render HTML, access the DVC remote, or call cloud document
services. No project credentials or repository secrets are required. GitHub
uses its automatic read-only token to check out this private repository.

To run the same extraction and test commands locally, use an environment with
Tesseract and Poppler installed:

```bash
python -m pip install -r requirements-ci.txt
python src/parse_text.py --params params.yaml --input tests/fixtures --output /tmp/lantern-smoke/parsed
python src/tables.py --params params.yaml --input tests/fixtures --output /tmp/lantern-smoke/tables
python -m pytest -q
```

The PR check is named `Fixture smoke tests / smoke`. A green check reports the
smoke job's result; making it a mandatory merge condition depends on repository
protection settings and the organization's GitHub plan. A successful local run
does not establish the issue's required green GitHub Actions run.
## Refresh filings after the embedded-image fix

The downloader decodes SEC's uuencoded binary attachments, and the renderer opens
`unpacked/<original filename>` so relative image paths resolve. Rendering fails
if an HTML image cannot load, rather than saving a broken-image placeholder.
For existing downloads, rerun in this order:

```bash
python src/download.py
python src/render.py
python src/parse_text.py
```

Regenerate other downstream artifacts as needed because source PDF hashes change.
The verified Apple page counts remain 61 (10-K) and 30 (10-Q).

## P8: initial DVC pipeline (issue #35)

Activate the Python environment and install the Python/system dependencies
described above, including Playwright Chromium, Poppler, and Tesseract. From the
repository root:

```bash
source .venv/bin/activate
dvc repro
dvc repro
dvc status
dvc dag
```

The pipeline is `download -> render -> parse_pdfplumber`, producing `data/raw/`,
`data/rendered/`, and `data/parsed/`. The first run needs SEC network access when
raw data is absent from the local DVC cache. With unchanged inputs and outputs,
the second run skips all three stages. DVC tracks each stage's script, shared
requirements, relevant parameter keys, and upstream data. Changing only `ocr`
parameters invalidates text extraction; changing download inputs can propagate
through the pipeline.

Commit `dvc.yaml`, the generated `dvc.lock`, and DVC initialization files to Git.
Generated data and `.dvc/cache/` stay out of Git. Back up any existing untracked
outputs before the first run: DVC may replace a stage's output directory when
rerunning it. After changing a script or parameters, use `dvc repro` to refresh
the data and lock file together.

The S3 remote (#48), fixture-only GitHub Actions (#36), and remaining stages
(#46/#54) are separate work. Until a remote is configured and populated, a fresh
clone must generate these outputs locally; `dvc pull` cannot fetch them yet.
