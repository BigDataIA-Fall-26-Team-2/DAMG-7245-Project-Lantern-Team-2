# Part 4: Docling vs the traditional pipeline

**Docling:** 2.134.0, `PdfPipelineOptions(do_ocr=False)`, TableFormer `accurate` (`params.yaml: docling`).
**Traditional path:** pdfplumber text (P1) + hybrid Camelot/pdfplumber tables (P2) + LayoutParser EfficientDet layout and routing (P3).
**Corpus:** AAPL FY2025 10-K (61 pages), Q3 FY2026 10-Q (30 pages), plus the P0 fixtures.
**Outputs:** `data/docling/` from `src/docling_parse.py` (stage `parse_docling`).

All Docling boxes are converted to the team frame before any comparison: bottom-left -> top-left origin, plus a per-page
cropbox offset. Docling measures from the cropbox, pdfplumber from the mediabox; the offset is 0 on every Apple page and
(15.5, 63.9) pt on the rotated multicolumn fixture, where converted boxes then match pdfplumber word positions within ~1.5 pt.

## 1. Comparison

| Dimension | Traditional | Docling | Evidence |
|---|---|---|---|
| Text accuracy (WER / CER) | TBD (P9) | TBD (P9) | Guna's eval on the same ground-truth pages |
| Table cell F1 | TBD (P9) | TBD (P9) | Guna's eval |
| XBRL match rate | TBD (P11) | TBD (P11) | Dhruvi's xbrl.py on both table paths |
| Statement tables (4 pages, 243 cells) | 243 cells | 243 cells, **0 differ** | `prototyping/shravya/income_diff.txt` |
| Usable tables found | 10-K 17, 10-Q 12 (layout-routed) | 10-K **31**, 10-Q **23** | P3 `layout_audit.md` s5; Docling run |
| 10-K balance sheet (p34) | no layout Table box; reached only via P2 page-level extraction | found directly; totals balance (359,241 / 364,980) | `data/docling/tables/AAPL_10K_20250927_p0034_t1.csv` |
| Reading order, 4-column dark spread | correct only after 3 fixes (invert, mediabox, column clustering); 8 blocks | correct out of the box; **16 blocks**, incl. both headings and 2 paragraphs P3 missed | `prototyping/shravya/reading_order_multicolumn.txt` |
| Character order in decorative text | names not captured | signer names scrambled ("u h S y k e h S e f f r") | same file, blocks b014, b016 |
| Footers and footnotes | page footer needs a regex (`is_footer`) | labels `page_footer` / `footnote` natively | `{stem}.blocks.jsonl` (`docling_label`) |
| Provenance | page + bbox per block (P3) | page + bbox per item, built in | both `blocks.jsonl` files |
| Throughput (wall time, M-series CPU) | layout stage several minutes, dominated by Camelot routing | 10-K 59 s, 10-Q 34 s (~1 s/page) | P10 will benchmark properly |
| Control | every step tunable and inspectable | pipeline options only | |

## 2. Where they agree, and why that matters

On the four main statements (10-K and 10-Q income statement and balance sheet), both paths produce **identical** team-format
tables: 57 + 54 + 76 + 56 = 243 cells, 0 different values, 0 missing on either side. Part of this is by design: both table
paths go through the same P2 `tables.to_long` with the full page text, so labels, period labels and scaling are shared; what
agrees is the cell structure and numbers each extractor found. Expect the XBRL match rate on these statements to be the
same for both paths; differences, if any, will come from other tables.

## 3. HTML vs rendered PDF (Part 4 task 2)

The 10-K's original iXBRL HTML was also converted (`data/docling/AAPL_10K_20250927.html.md`; analysis in
`prototyping/shravya/html_vs_pdf.txt`):

| | Rendered PDF | Original HTML |
|---|---|---|
| Tables | 48 | 62, of which **8 completely empty** (layout spacers) |
| Columns per table (median / max) | **4 / 8** | **18 / 42** |
| Net income 2025 / 2024 / 2023 | 112,010 / 93,736 / 96,995 | identical (in 3 tables: income, comprehensive income, cash flow) |
| Page numbers and boxes | yes | **none** (HTML has no pages) |
| Conversion time | 59 s | 10 s |

Rendering changed **table structure, not content**. HTML tables carry spacer rows, `$` in its own cell, empty layout tables
and colspan cells that Docling duplicates across every spanned column. The rendered PDF gives cleaner tables and is the only
version with page + bbox provenance, which Lina's traceability requirement needs.

## 4. Recommendation to Lina (provisional until the P9/P11 metrics are in)

Use **Docling as the primary parser** and keep the **traditional path as the fallback and cross-check**. Docling found nearly
twice as many usable tables (54 vs 29), recovered the balance sheet the layout detector missed, read a dark four-column
spread correctly without any of the three fixes the traditional path needed, labels footers and footnotes natively, and
converts a filing in about a minute with page-level provenance built in. On the four financial statements the two paths
agree cell for cell, so running both on statement pages costs little and gives an independent check before XBRL validation.
Keep the traditional path where control matters: its steps can be tuned and inspected individually, pdfplumber reads the exact
text layer, and it is the fallback when Docling garbles decorative text (scrambled signer names on the fixture). Final
choice to be confirmed against WER, cell F1 and XBRL match rate for both paths.

## 5. Limitations
- Statement agreement partly reflects the shared `to_long` post-processing (labels, periods, scale), not Docling's own label reading.
- Reading-order evidence is one fixture page; Apple's pages are single-column.
- Throughput numbers are single wall-clock runs, not benchmarks (Part 10).
- 17 + 7 Docling tables had no rows with two or more numbers after `to_long`; not yet inspected individually.
