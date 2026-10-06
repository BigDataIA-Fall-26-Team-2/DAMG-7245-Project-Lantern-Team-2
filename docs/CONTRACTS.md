# LANTERN shared contracts

Shapes every stage's script must produce/consume identically. Internal-only details stay in each owner's own code, not here.

## File stems

`{ticker}_{form}_{YYYYMMDD}`, date = filing/period-end date from the manifest. Examples:
- `AAPL_10K_20250927` — FY2025 10-K, accession `0000320193-25-000079`
- `AAPL_10Q_20260627` — Q3 FY2026 10-Q, accession `0000320193-26-000020`

`doc_id` = the accession number, taken from the manifest (not re-derived from the stem).

## Pages and boxes

- Pages are **1-based**.
- `bbox` is `[x0, top, x1, bottom]` in points, **top-left origin**. If your tool returns bottom-left origin (e.g. PDF native), convert inside your own script before it crosses a stage boundary.

## Table CSV

Path: `data/tables/{stem}_p{NNNN}_t{K}.csv` (`NNNN` = zero-padded page, `K` = table index on that page, both 1-based).

Columns: `row_label, col_label, raw, value, scale`

## Block schema

Emitted per detected layout block: `page, block_id, block_type, bbox, score, model`

## Shared functions

- `tables.extract_best_df(pdf_path, page, bbox=None)` — returns `(df, info)`. `df` is the best table on the page in the table CSV format above (`row_label, col_label, raw, value, scale`), or `None` if no candidate is accepted. `info` = `{method, score, extractor_version, accepted, skipped_rows}`; use `method` and `extractor_version` for the Part 5 `extractor` fields. `bbox` = `[x0, top, x1, bottom]` in points, top-left origin (converted for Camelot inside).
- `managed.managed_fallback(page_image, ocr_conf)` — returns managed-OCR output when local OCR confidence is low.

Thresholds (`accept_score`, `ocr_conf` cutoffs, etc.) live in `params.yaml`, not here.
