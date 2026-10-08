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

**Bug found end to end, now fixed:** on 10-K p32, routing a Table box returned an accepted table (score 1.0) with
Net income `112010.0`, `scale 1.0` and period labels `col1/col2/col3`, because `extract_best_df` read only the text inside
the box, and the "(In millions...)" note and the period headers sit above it. Fixed in `tables.py` by PR #106: the bbox
still chooses the table, but `to_long` reads the full page. `tests/test_layout_routing.py` routes a numbers-only box
below the headers (like the detector's p32 box) through `route_table`: it failed before #106 ("period headers lost")
and passes after, with Net income 112,010,000,000 and FY period labels. `tests/test_tables_bbox.py` (#106) covers
`extract_best_df` directly.

## 6. Layout-aware extraction demo (multi-column)

**Page:** `tests/fixtures/multicolumn.pdf`, Amdocs Annual Report 2024 (SEC-filed PDF), page 6 = printed spread 10-11
(source per `docs/ai_log/lokesh.md`). Two printed pages side by side, **4 text columns**, white text on a dark designed background.

**Plain pdfplumber** (`page.extract_text()`, first lines) reads straight across the spread and braids the columns together:

    ESG: Seeking to make a difference Healthy pipeline and innovative technology
    position Amdocs for continued growth and
    As we work with our customers and We place high value on protecting the operating margin expansion
    partners to create a better-connected environment and minimizing negative
    ...
    While we continue to operate in a We remain confident in our relatively

**Layout pipeline** (`src/layout.py`), blocks in reading order:

| block | column | x0 (pt) | starts with |
|---|---|---|---|
| p0001_b001 | 1 | 56 | ESG: Seeking to make a difference (Title) |
| p0001_b002 | 1 | 52 | As we work with our customers and partners... |
| p0001_b003 | 1 | 53 | Our achievements have been recognized... |
| p0001_b004 | 2 | 211 | We place high value on protecting the environment... |
| p0001_b005 | 2 | 209 | We also place great emphasis on enriching... |
| p0001_b006 | 3 | 437 | While we continue to operate in a challenging... |
| p0001_b007 | 3 | 436 | Our cloud-related activities in fiscal 2024... |
| p0001_b008 | 4 | 595 | We remain confident in our relatively resilient... |

Getting there required three fixes, each verified on this page and checked not to change the Apple filings
(block counts identical before and after on both filings):

1. **Dark pages are inverted before detection.** Unmodified, the detector returned one Figure box over the whole spread.
   Page brightness is 0.18 vs 0.87-0.96 for every Apple page checked, so pages below `dark_page_brightness: 0.5` are
   colour-inverted: 0 -> 7 Text blocks. Records carry `inverted: true`.
2. **The full mediabox is rendered.** The page has `/Rotate 90` and a cropbox smaller than its mediabox. pdfplumber renders
   only the cropbox by default (1587x1013 px) but reports text coordinates in the mediabox frame (1650x1275 px expected at
   150 DPI), so every box was shifted ~16 pt left and ~64 pt up, pulling headings into paragraphs and slicing lines.
   Rendering with `force_mediabox=True` fixes it; `detect_page` now raises an error if the rendered size ever differs from
   the expected size.
3. **Columns are found by clustering block left edges.** The original rule (left vs right half of the page) mixed columns
   1/2 and 3/4. Left edges are sorted and a new column starts at any jump larger than `column_gap_pt: 50`
   (gaps on this page are 150+ pt). Single-column Apple pages stay one column.

**Still missed by the detector on this page:** the right page's heading and two paragraphs (columns 3 and 4); logos and
signatures are unboxed.

## 7. Known limitations
- Straddling and split boxes garble or fragment some paragraphs; documented, not fixed (a model limitation).
- A few boxes are offset by more than 8 pt and still clip a letter.
- Multiple tables under one Table box (10-K p50) can only yield the single best table.
- These failure modes are the comparison baseline for Docling (Part 4).
