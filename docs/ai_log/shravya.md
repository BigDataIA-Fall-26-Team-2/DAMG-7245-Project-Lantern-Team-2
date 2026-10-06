# Shravya AI Engineering Log

## P3 environment setup

- Tool: Claude (Anthropic), claude.ai chat. Suggested building the team `.venv` from an existing conda Python 3.11 (which already provides Tesseract and Poppler) instead of Homebrew, which compiles from source on macOS 14.
- Verification: `pip check` clean; README import check printed `Imports OK`; Tesseract 5.5.2 and Poppler 26.09.0 match the versions verified in the README. Before/after `pip freeze` diff when adding LayoutParser showed 17 packages added and none changed.
- Changes: `pikepdf==10.16.0` has no macOS 14 wheel and fails to build (missing qpdf headers), so I installed a pre-built pikepdf 10.13 locally and installed the rest from a copy of `requirements.txt` without that pin. The team file was not changed for this.
- Limitation: `opencv-python` (LayoutParser) and `opencv-python-headless` (Camelot) are both installed. They are the same version and `cv2`, `camelot` and `layoutparser` import together, but two OpenCV packages sharing one folder is fragile. Verified on macOS 14 arm64 only.
- Confidence: high for the local setup; Linux clean-room install unverified.

## P3 layout model loading

- Tool: Claude. Diagnosed why `AutoLayoutModel` failed: LayoutParser's built-in Dropbox link returns a ~205 kB web page instead of the ~45 MB weights. Suggested the LayoutParser team's Hugging Face repo and drafted `load_model()` with an automatic download.
- Verification: downloaded file is 45 MB; the model loads and reports the PubLayNet label map {1: Text, 2: Title, 3: List, 4: Table, 5: Figure}.
- Changes: PyTorch 2.6 refuses the checkpoint in weights-only mode because it also stores training args and numpy types. Instead of `weights_only=False`, I allowlisted exactly the types PyTorch named (`argparse.Namespace`, numpy scalar and dtype classes), adding them one at a time as each error reported the next. Replaced `lp.draw_box`, which breaks on current Pillow (`getsize` removed), with a small PIL drawing function.
- Limitation: depends on the Hugging Face URL staying up; `models/` is gitignored.
- Confidence: high.

## P3 detection, threshold and post-processing

- Tool: Claude. Drafted `detect_page`, duplicate removal, reading order, text routing with OCR fallback, sections, the footer filter, and the threshold and padding sweep scripts.
- Verification: I ran the threshold sweep on 9 mixed pages and chose 0.25 from the results (0.25/0.2/0.1 identical; 0.4 and 0.5 left 10-Q page 2 with no blocks). I ran the padding sweep and chose 8 pt (clipped starts 132 -> 35 on the 10-K), then spot-checked the 15 remaining cases by hand. Confirmed 10-Q page 7 is genuinely blank (0 characters, empty at threshold 0, checked visually). Checked reading order and text on 10-K page 10 against the page.
- Changes: overlaps removed by score kept the wrong box on 10-K page 10 (a straddling box beat the correct paragraph box), so I documented it as a detector limitation rather than tuning further. The section names were being taken from the page footer; I checked for running headers by counting repeated Title texts (none repeat on most pages) and added a footer-only filter. Added `pages.csv` so blank pages are recorded instead of faking a block.
- Limitation: AI estimates were wrong twice and I caught both: it expected ~60 footers (actual 9), and the practice "multi-column" fixture it picked turned out to be single-column, because its detection heuristic counted words on both page halves, which any full-width paragraph satisfies.
- Confidence: high for the code and measurements; layout quality itself is limited by the model (see audit).

## P3 detector audit and report

- Tool: Claude. Proposed the audit categories (correct / missed / wrong type / bad box), helped read overlays, and drafted `reports/layout_audit.md`.
- Verification: I opened all 10 overlay images and checked every count against the page; the summary script's totals (Text 21/55, Title 13/33, Table 1/32) match the per-page counts.
- Changes: added the "bad box" category, since box-extent errors were the most common failure and leaving them out would overstate quality. Excluded page footers from the counts and reported them separately.
- Limitation: counts are one person's judgement; block boundaries (e.g. grouping cover-page fields) involve calls another reviewer might make differently.
- Confidence: high that the failure patterns are real (tables boxed as numbers only, repurchase tables labeled Figure); moderate on exact counts. I can explain, modify, test and defend every part of this work.
