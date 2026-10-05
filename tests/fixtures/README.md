# Offline P0 fixtures

These small PDFs are committed to Git, not DVC. CI reads them directly: it does
not download SEC filings, access the DVC remote, or regenerate fixtures.
All source page numbers below are **1-based PDF pages**, not printed footers.

| File | Pages | Bytes | Source and purpose |
|---|---:|---:|---|
| scanned.pdf | 3 | 1,134,051 | Apple FY2025 10-K rendered pages 4, 32, 37 (printed 1, 29, 34): prose, income statement, accounting notes; OCR input |
| statement.pdf | 1 | 67,833 | Same Apple PDF, page 32 (printed 29): consolidated statements of operations; table extraction |
| multicolumn.pdf | 1 | 615,304 | Amdocs Annual Report 2024, original PDF page 6 (printed spread 10–11): four prose columns, sidebar graphic and signatures; layout/reading order |

## Provenance

Apple: accession `0000320193-25-000079`, fiscal period ending 2025-09-27.
Original iXBRL: https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm
Local source: `data/rendered/AAPL_10K_20250927.pdf`, rendered with Playwright
1.55.0, Letter (612 × 792 pt). Page 32 matches the existing P2 table bake-off.

Amdocs: Annual Report 2024, SEC exhibit `d865204dex991.pdf`, accession
`0001193125-24-281286`, CIK `1062579`.
Source: https://www.sec.gov/Archives/edgar/data/1062579/000119312524281286/d865204dex991.pdf
Retrieved 2026-10-05. This is a native PDF page, not a Playwright render.
The page is an original two-page spread stored as one PDF page; it is preserved
without cropping, reflow, or rescaling. Read the left spread's heading and two
columns first, then the right spread's heading and two columns; treat the
badge, signatures, and footers separately. This is a layout fixture only:
it does not add Amdocs to the two-filing Apple corpus or XBRL evaluation.
Apple's narrative pages inspected were single-column; numeric table columns
were not used as a substitute for multi-column prose.

## Rebuild (developer only)

Install root `requirements.txt` in Python 3.11 and install Poppler. Download the
external source to a temporary directory with the configured SEC User-Agent:

```bash
python - <<'PY'
from pathlib import Path
import requests, yaml
config = yaml.safe_load(Path('params.yaml').read_text())
d = config['download']
r = requests.get(config['fixtures']['multicolumn_url'],
                 headers={'User-Agent': d['user_agent_name'] + ' ' + d['user_agent_email']},
                 timeout=60)
r.raise_for_status()
Path('/tmp/lantern-amdocs-2024.pdf').write_bytes(r.content)
PY
python src/fixtures.py --params params.yaml --input data/rendered \
  --external /tmp/lantern-amdocs-2024.pdf --output tests/fixtures
python -m pytest -q tests/test_fixtures.py
```

The `fixtures` section of `params.yaml` pins source SHA-256 values, page choices,
and 200 DPI. A changed source (including a re-render with changed PDF metadata)
is rejected: visually recheck pagination before deliberately updating the hash.
The builder calls `pdftoppm` in grayscale PNG mode, then `img2pdf` without a
text layer, preserving the original Letter dimensions. Native pages are copied
with pypdf. The img2pdf internal engine avoids variable PDF identifiers; a second
build produced byte-identical PDFs for all three fixtures. Verified tools: Poppler 26.09.0, pypdf 6.19.0, img2pdf 0.6.3,
PyYAML 6.0.3. Other system-tool versions may change output bytes.

## Validation and limitations

All five fixture pages were rendered and visually inspected. Offline tests
verify the scan's page/image counts and absence of selectable text, the native
statement's heading and a numeric anchor, and substantial text in each of the
external page's four columns. These are artifact sanity checks, not OCR WER,
table accuracy, or a proof of correct reading-order extraction.
The scan is a clean synthetic rasterization, not a real degraded photocopy.
Ground-truth transcription and table CSVs belong to P9 (`gt/`); no parser output
has been promoted to ground truth here.
