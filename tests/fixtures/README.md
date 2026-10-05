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

## Preparation record

Codex prepared these PDFs as a one-time task:

- Rasterized Apple PDF pages 4, 32, and 37 with `pdftoppm` at 200 DPI in
  grayscale PNG mode, then combined them with `img2pdf` into an image-only
  PDF preserving Letter dimensions (612 × 792 pt).
- Extracted Apple page 32 and Amdocs page 6 with pypdf, preserving native
  text and layout.
- Used Poppler 26.09.0, pypdf 6.19.0, and img2pdf 0.6.3. The img2pdf
  internal engine and disabled date metadata produced repeatable output.

No fixture-generation script or pipeline stage is required. The finished PDFs
are the inputs; tests consume them directly. If replacing them later, verify
source pagination visually and update this provenance record.

Source SHA-256 values used during preparation:

- Apple rendered PDF: `d4b8c0b3a643378938e7c6277039ac7c50e0135743acd8955230dd654fd16066`
- Amdocs original PDF: `9921801eb9f4100083918555a8f9908cd179d0ef540fd5f407044f0309deb604`

## Validation and limitations

All five fixture pages were rendered and visually inspected. Offline tests
verify the scan's page/image counts and absence of selectable text, the native
statement's heading and a numeric anchor, and substantial text in each of the
external page's four columns. These are artifact sanity checks, not OCR WER,
table accuracy, or a proof of correct reading-order extraction.
The scan is a clean synthetic rasterization, not a real degraded photocopy.
Ground-truth transcription and table CSVs belong to P9 (`gt/`); no parser output
has been promoted to ground truth here.
