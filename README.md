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
| Camelot (camelot-py) + OpenCV (opencv-python-headless) | P2: table bake-off (lattice/stream/network/hybrid) and hybrid extractor | requirements.txt |
| pandas | P2/P11: table CSVs and XBRL value comparison | requirements.txt |
| Arelle (arelle-release) | P11: iXBRL fact extraction | requirements.txt |
| difflib | P11: fuzzy label-to-concept matching | Python standard library |
| Streamlit | App: team UI (frontend/) | requirements.txt |
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
python -m pip check
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

This verifies the local prerequisite only. Linux reproduction, the DVC pipeline,
S3 access, and project regression tests remain separate work; those stages and
tests do not yet exist on main. The download/render implementation remains in
PR #88 and is not included in this environment branch.

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
