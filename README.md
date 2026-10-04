# DAMG-7245-Project-Lantern-Team-2

Case Study 1 (DAMG 7245, Fall 2026): a reproducible pipeline that turns raw SEC 10-K/10-Q filings into a layout-aware, XBRL-validated corpus, versioned end-to-end with DVC.

- Team workflow and review process: [CONTRIBUTING.md](CONTRIBUTING.md)
- Part-by-part ownership and milestones: [WORKPLAN.md](WORKPLAN.md)
- AI-assistant rules for this repo (tool-agnostic — Claude, Codex, etc.): [SKILLS.md](SKILLS.md)

Full project summary, architecture diagram, reproduction steps, and the Codelab/demo links go here once the pipeline exists (required before submission, per Case Study 1 Section 8.2).

## Tools in use

| Tool | Used for | Pinned in |
|---|---|---|
| sec-edgar-downloader | Fetching raw 10-K/10-Q filings from EDGAR (`src/download.py`) | `requirements.txt` |
| Playwright | Rendering filings to PDF (`src/render.py`) | `requirements.txt` |
| PyYAML | Reading `params.yaml` | `requirements.txt` |
| pypdf | Reading back each rendered PDF's actual page size for `manifest.csv` (`src/render.py`) | `requirements.txt` |
| pytest | Offline download-selection and rerun regression checks | `requirements.txt` |
<!-- Add one row per new tool/library the moment you introduce it (see SKILLS.md). -->

## P0 corpus and reproduction

The corpus is exactly one Apple 10-K and one Apple 10-Q:

| Form | Fiscal period end | Accession | PDF stem |
|---|---|---|---|
| 10-K | 2025-09-27 | 0000320193-25-000079 | AAPL_10K_20250927 |
| 10-Q | 2026-06-27 | 0000320193-26-000020 | AAPL_10Q_20260627 |

`params.yaml` pins the date window, `limit: 1` per form, and expected accessions
and fiscal periods. The downloader verifies the returned corpus against those
pins. Each filing retains its original primary iXBRL filename next to its XSD
and linkbases under `unpacked/`. The manifest includes accession/doc_id, CIK,
original source path, ticker, form, period, PDF path, and renderer details.

With Python 3.11 and an activated virtual environment:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python src/download.py --params params.yaml --output data/raw
python src/render.py --params params.yaml --input data/raw --output data/rendered
python -m pytest -q
```

Existing raw directories containing other filings, or rendered directories
containing other PDFs, are rejected. Archive those output directories outside
`data/` before migrating an older corpus, then run these commands with clean
output directories. Matching-corpus reruns are supported: the downloader
re-fetches deleted submission bundles before unpacking; rendering overwrites
the same two PDFs and rebuilds the manifest. Raw and rendered data remain
local/ignored until the separate DVC integration lands.
