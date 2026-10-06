# Part 3: Layout detection audit

**Model:** LayoutParser 0.3.4, EfficientDet-D0 trained on PubLayNet (`lp://efficientdet/PubLayNet/tf_efficientdet_d0`).
Weights from the LayoutParser team's Hugging Face repo (the built-in Dropbox link is dead); `src/layout.py` downloads them if missing.
Pages are rendered at 150 DPI for detection; boxes are converted to PDF points (×72/150), top-left origin, per `docs/CONTRACTS.md`.

**Corpus:** AAPL FY2025 10-K (61 pages) and Q3 FY2026 10-Q (30 pages).

## 1. Score threshold

The default 0.5 dropped most real blocks. Sweep on 9 pages of mixed type (cover, prose, statements, notes), blocks kept per threshold
(`prototyping/shravya/threshold_sweep.csv`):

| Page | 0.10 | 0.20 | 0.25 | 0.30 | 0.40 | 0.50 |
|---|---|---|---|---|---|---|
| 10-K p1 (cover) | 8 | 8 | 8 | 6 | 3 | 1 |
| 10-K p10 (prose) | 7 | 7 | 7 | 7 | 3 | 1 |
| 10-K p20 (prose) | 12 | 12 | 12 | 8 | 4 | 2 |
| 10-K p32 (income stmt) | 9 | 9 | 9 | 6 | 3 | 1 |
| 10-K p34 (balance sheet) | 4 | 4 | 4 | 4 | 3 | 1 |
| 10-K p50 (notes) | 9 | 9 | 9 | 7 | 6 | 5 |
| 10-Q p2 | 1 | 1 | 1 | 1 | 0 | 0 |
| 10-Q p4 (income stmt) | 3 | 3 | 3 | 1 | 1 | 1 |
| 10-Q p15 (notes) | 18 | 18 | 18 | 9 | 4 | 1 |

**Decision: `score_threshold: 0.25`.** 0.25, 0.20 and 0.10 are identical on all 9 pages, so 0.25 is the strictest value that loses nothing.
At 0.30, 6 of 9 pages lose blocks; at 0.40/0.50, 10-Q p2 has no blocks at all.
Duplicates are removed by keeping the higher-scoring box when more than 50% of the smaller box overlaps (`max_overlap: 0.5`).

Full run at 0.25: 10-K 518 blocks, 10-Q 255 blocks. Every page is listed in `data/layout/{stem}.pages.csv`;
10-Q p7 is recorded as `blank` (0 characters, visibly empty apart from a page-break rule). No page has text but no blocks (`missed`).

## 2. Text padding

Detector boxes often sit a few points off the text, clipping first/last letters ("he Company", "Ris" for "Risks").
Text inside each box is read with pdfplumber after widening the box horizontally only (vertical padding would pull in neighbouring lines).
Proxy metric: text blocks starting with a lowercase letter (`prototyping/shravya/text_pad_sweep.csv`):

| pad (pt) | 0 | 2 | 4 | 6 | 8 | 12 |
|---|---|---|---|---|---|---|
| 10-K | 132 | 94 | 67 | 46 | 35 | 26 |
| 10-Q | 51 | 36 | 26 | 13 | 10 | 10 |

**Decision: `text_pad_pt: 8`** (-73% on the 10-K, -80% on the 10-Q). The 10-Q flattens at 8; 12 pt gains little and risks crossing a column gap.
Total characters read rise only ~100-200 per step, so padding isn't pulling in neighbouring text.
Spot check of the 15 remaining 10-K cases at 8 pt: 3 still clipped, 3 are Apple product names (iPhone, iPad), 9 are legitimate mid-sentence starts.

## 3. Detector audit (10 pages)

Judged by eye from the overlays in `reports/layout/`; per-page counts and notes in `prototyping/shravya/layout_audit.csv`.
**Correct** = right label, right extent. **Missed** = real block with no box. **Wrong type** = box on a real block with the wrong label
(counted under the class it should have been). **Bad box** = right label but wrong extent (cuts words or lines, merges or splits blocks, or covers nothing).
Page footers are excluded (handled separately, see 4).

Pages: 10-K 1, 10, 20, 22, 32, 34, 50; 10-Q 4, 15, 28.

| Class | Correct | Missed | Wrong type | Bad box | Correct rate |
|---|---|---|---|---|---|
| Text | 21 | 18 | 2 | 14 | 38% (21/55) |
| Title | 13 | 13 | 4 | 3 | 39% (13/33) |
| Table | 1 | 4 | 21 | 6 | 3% (1/32) |
| List | 0 | 0 | 0 | 0 | none on audited pages |
| Figure | 0 | 0 | 0 | 0 | no real figures on audited pages |

### Failure modes
- **Tables are the weakest class.** Only the 10-Q income statement (p4) was boxed correctly. On the 10-K income statement (p32) and segment note (p50)
  the Table box covers the number columns only, with row labels split into separate Text boxes. The 10-K balance sheet (p34) has no Table box at all.
  Small tables inside notes (10-Q p15) are missed and their rows boxed as Text or Title.
- **Repurchase tables are labeled Figure** (10-K p22, 10-Q p28). Apple's filings contain essentially no real figures, so the Figure class mostly catches this one table layout.
- **Paragraph boundaries in closely spaced prose are unreliable:** boxes start mid-paragraph, cut last lines, merge neighbours, or straddle two paragraphs.
  A straddling box slices lines mid-height and produces interleaved text (10-K p10 block 5). This is a detector error that post-processing can't fully fix.
- **Headings are mixed:** bold "Item X." headings are mostly found (10-K p20); italic risk headings and statement titles are often missed or labeled Text.
- **Form-style pages** (the cover) are largely unboxed: short labels and fields don't resemble PubLayNet's research-paper layouts.
- **Domain shift:** PubLayNet is biomedical journal articles; 10-K layout (statements, forms, dense notes) is outside its training distribution.

## 4. Post-processing in `src/layout.py`
- **Reading order:** left column before right (a block starting in the right half is right-column), then top to bottom; `block_id`s follow this order.
- **Sections:** each block takes the most recent Title text in reading order, carried across pages.
- **Footer filter:** the running footer ("Apple Inc. | 2025 Form 10-K | N") was detected as a Title on 9 pages and hijacked section names.
  Blocks matching `Form 10-[KQ] | <n>` are flagged `footer: true` and never become a section.
- **Text routing:** Text/Title/List boxes go to pdfplumber (padded crop); if empty, the crop is OCR'd with Tesseract at `ocr.dpi` (`ocr: true`).
- **Figures:** cropped to `data/figures/`. Note: the two checked "figures" are repurchase tables (see 3).

## 5. Table routing

Table blocks are sent to `tables.extract_best_df(pdf_path, page, bbox)` (Part 2, PR #93), which returns `(df, info)` in the
contract table format. Before routing, each Table box is **stretched to the full page width** and padded vertically by
`pad_pt` (2 pt), because the audit showed Table boxes often cover only the number columns (10-K p32, p50).
The detector's own box stays in `bbox`; the box actually sent is stored as `table_info.routed_bbox`.
Every block now carries `extractor` / `extractor_version` (the table method for tables, pdfplumber or tesseract for text).

| Filing | Table blocks | Accepted | Errors | Winning method |
|---|---|---|---|---|
| 10-K | 36 | 17 (47%) | 0 | camelot-stream x17 |
| 10-Q | 19 | 12 (63%) | 0 | camelot-stream x11, pdfplumber-text x1 |

- Both income statements are accepted with score 1.0 and keep their row labels (10-K p32: 57 rows; 10-Q p4: 76 rows).
  Without the full-width stretch, the 10-K p32 box covers numbers only.
- Rejections are mostly the extractor correctly refusing non-tables: e.g. the Table box over empty space on 10-K p22.
- The 10-K balance sheet (p34) is absent because the detector drew no Table box there. Financial statements therefore keep
  Dhruvi's heading-based page extraction as the primary path; layout routing adds the other tables.

**Bug found end to end:** on 10-K p32, Net income comes back as `112010.0` with `scale 1.0` instead of `112010000000`.
With a bbox, the scale caption "(In millions...)" sits above the table box, so it falls outside the text the extractor reads.
On 10-Q p4 the caption falls inside and the value is scaled correctly. Reported to the Part 2 owner: the scale lookup
should use the full page text even when a bbox is passed.

## 6. Known limitations
- Straddling and split boxes garble or fragment some paragraphs; documented, not fixed (a model limitation).
- A few boxes are offset by more than 8 pt and still clip a letter.
- Multiple tables under one Table box (10-K p50) can only yield the single best table.
- These failure modes are the comparison baseline for Docling (Part 4).
