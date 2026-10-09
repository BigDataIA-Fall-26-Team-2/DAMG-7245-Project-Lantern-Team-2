# Offline P0 fixtures

These PDFs are committed to Git, not DVC, so the fixture smoke workflow can run
without EDGAR downloads, DVC remote access, or cloud credentials. Page selections
below are **1-based PDF pages**, not printed page numbers.

| File | Pages | Bytes | Source pages and purpose |
|---|---:|---:|---|
| `scanned.pdf` | 3 | 1,134,051 | Apple FY2025 10-K rendered pages 4, 32, 37 (printed 1, 29, 34), in that order: prose, income statement, and accounting notes; exercises OCR |
| `statement.pdf` | 1 | 67,833 | Apple FY2025 10-K rendered page 32 (printed 29), consolidated statements of operations; exercises table extraction |
| `multicolumn.pdf` | 1 | 615,304 | Amdocs Annual Report 2024 PDF page 6 (printed spread 10–11); four prose columns for layout and reading-order checks |

## Source provenance

**Apple:** accession `0000320193-25-000079`, CIK `0000320193`, fiscal period
ending September 27, 2025. The [original iXBRL filing](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm)
was rendered to `data/rendered/AAPL_10K_20250927.pdf` using Playwright 1.55.0,
Letter pages (612 × 792 PDF points). The render manifest records that source
and renderer. Recheck page contents before preparing fixtures from a new render:
browser or rendering changes can move the page boundaries.

**Amdocs:** [Annual Report 2024, SEC exhibit `d865204dex991.pdf`](https://www.sec.gov/Archives/edgar/data/1062579/000119312524281286/d865204dex991.pdf),
accession `0001193125-24-281286`, CIK `1062579`, retrieved October 5, 2026.
This is a native PDF, not a Playwright render. Its page 6 contains two printed
pages as one spread and was preserved without cropping, reflow, or rescaling.
The inspected Apple narrative pages were single-column, so this external page
supplies the required multi-column fixture. Amdocs is not part of the two-filing
Apple corpus or its XBRL evaluation.

Read the left spread's heading and two columns first, then the right spread's
heading and two columns. Treat the badge, signatures, and footers separately.

## Preparation method

The fixtures were prepared once on October 5, 2026:

1. Rasterize Apple pages 4, 32, and 37 separately with Poppler `pdftoppm`, using
   `-f N -l N -r 200 -gray -png -singlefile` for each selected page.
2. Combine the three PNGs in that order with `img2pdf`, using
   `pagesize=(612, 792)`, `nodate=True`, and `engine=img2pdf.Engine.internal`.
   The resulting PDF has images only, with no selectable text layer.
3. Copy Apple page 32 and Amdocs page 6 into separate one-page PDFs using
   `pypdf.PdfWriter.add_page`, preserving their native text and page geometry.

Recorded preparation versions: Poppler 26.09.0, pypdf 6.19.0, and img2pdf 0.6.3.
The original builder is retained in Git history at
`51bcc8d:src/fixtures.py`, with its source hashes and selections in that commit's
`params.yaml`. It is not a current pipeline stage or a required CI command.
Different renderers or tool versions may produce different PDF bytes.
See the [October 5 preparation log](../../docs/ai_log/lokesh.md) for the original
visual checks and the reason the img2pdf internal engine was selected.

## Integrity and ground truth

SHA-256 values of the committed fixtures, verified October 9, 2026:

```text
4a84ae05c494224d3542e1f0c920dac8d8a5e0222531d64f6a136034f254981c  scanned.pdf
4e8a38d8b6259eb544e71a839416fa5368f7d83c2fda7f4ae1ae701aea1b76cb  statement.pdf
d81a0e67b12063ccff87cf82c57ba91cf6d0cb6c4b959c7866092159df50a538  multicolumn.pdf
```

P9 owns the transcriptions, table CSV, and [ground-truth conventions](gt/CONVENTIONS.md).
`scanned_p1.gt.txt` covers the first scanned page only (Apple rendered page 4);
`statement_p1.gt.txt` and `statement_p1_t1.gt.csv` cover the statement fixture;
`multicol_p1.gt.txt` covers the Amdocs spread. There are no committed
transcriptions for scanned pages 2 and 3. The scan is a clean synthetic
rasterization, not a degraded photocopy.

Run the existing fixture quality checks from the repository root after installing
the documented Python and system dependencies:

```bash
python -m pytest tests/test_fixture_quality.py -q
```

Those checks run text and table extraction into temporary output directories
when smoke-workflow outputs are not supplied. They measure the traditional
fixture outputs; they do not establish Docling or layout-path accuracy.
