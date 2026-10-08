# Lokesh AI Engineering Log

## Issue #11 — Python 3.11 environment

- Tool: Codex (GPT-6). Created the isolated environment, pinned its dependencies, and drafted setup documentation.
- Verification: `pip check` passed; P0 scripts and P1/P8 package imports passed; Chromium rendered a synthetic page, pdfplumber extracted its text, Poppler rasterized it, Tesseract recognized `LANTERN 12345`, and img2pdf produced a readable one-page image-only PDF. DVC and pytest version commands passed.
- Changes: selected installed Python 3.11.11 explicitly instead of the shell's Python 3.14; reused installed Tesseract, Poppler, and Chromium; retained the four dependency versions already pinned by PR #88. Added tools for the assigned P0/P1/P8 scope and froze resolved dependencies.
- Limitation: verified on macOS arm64 only; no Linux clean-room run, cloud access, DVC pipeline run, or project tests were claimed. Existing P0 scripts were imported from the original checkout, since they are not merged into main. No data downloads or cloud services were invoked.
- Confidence: high for the observed local setup; cross-platform and full-pipeline reproduction remain unverified. Author must review this entry and be able to explain, modify, test, and defend the changes before submission.


## Shared dependency-file consolidation

- Tool: Codex (GPT-6). Moved all 122 existing pins unchanged into the shared root `requirements.txt`, removed per-person files, and updated setup commands and tool references.
- Verification: compared the exact dependency lists before and after on every affected branch; checked installation against the existing Python 3.11 environment and ran the P0 regression tests. No package versions changed.
- Limitation: this reorganizes the verified local environment; Linux clean-room reproduction remains unverified. Author review remains required.


## 2026-10-05 — Issue #15: offline PDF fixtures

- **Tool/model:** Codex (GPT-6).
- **Contribution:** Selected source pages and prepared three Git-tracked PDFs: `scanned.pdf` (Apple FY2025 10-K rendered pages 4, 32, 37, rasterized at 200 DPI), `statement.pdf` (Apple rendered page 32), and `multicolumn.pdf` (SEC-filed Amdocs Annual Report 2024 PDF page 6, printed spread 10–11). Used pdftoppm and img2pdf for the scan and pypdf for native-page extraction.
- **Final deliverables:** The three PDFs and this AI log entry. At the author’s request, removed the temporary generator, fixture parameters, optional fixture test file, fixture README, and root README additions. No reusable fixture-generation code or fixture-specific tests remain in this PR.
- **Verification performed during preparation:** Visually inspected all five output pages and checked that the scan has three image-only pages, the statement retains text, and the external spread has four prose columns. Rebuilding produced byte-identical PDFs, and the final scan rendered identically to the inspected version. Total fixture size: 1,817,188 bytes. These were preparation checks; their temporary automation is not a delivered test suite.
- **Current validation:** After removing the optional fixture tests, the remaining repository suite passed 10 tests. The earlier 13-test run included three now-removed fixture tests and does not describe the current suite. PDF contents were unchanged by the removals.
- **Failure/fix:** The default img2pdf backend changed PDF bytes between runs despite date suppression; selecting its internal backend fixed this during preparation. Full test collection initially lacked the already-pinned pandas dependency locally; installing it under root requirements constraints resolved collection.
- **Limits:** The Amdocs page is a layout fixture only, outside the two-filing Apple corpus. Scans are clean synthetic rasterizations, not degraded photocopies. Issue #15’s requested fixture provenance README is omitted at the author’s request. No OCR accuracy, P9 ground-truth completeness, or Linux reproduction is claimed.
- **Confidence/responsibility:** High confidence in the observed fixture structure and preparation checks. Author review and ability to explain, modify, test, and defend the delivered PDFs remain required.

## 2026-10-05 — P1: native text and OCR fallback (issues #16, #28)

- **Tool/model:** Codex (GPT-6). Implemented `src/parse_text.py`, independent character-count/junk-token OCR signals, Tesseract text and word boxes, pixel-to-point conversion, per-page text/word output, and decision logging. Added targeted P1 regression tests and usage documentation; dependencies already exist in shared root requirements.
- **Verification:** Live local extraction produced 91 text files from the two Apple PDFs: 90 native pages and one OCR attempt on 10-Q page 7. That page returned empty text and was visually confirmed blank. Fixture run: three scanned pages used OCR with 3,620 / 1,194 / 2,759 output characters and mean confidence 94.27 / 92.51 / 95.38; statement and multi-column pages stayed native. All emitted boxes were checked against displayed page dimensions. Regression checks cover independent triggers, coordinate scaling/line grouping, native routing, rotated pages, output identities, stale page cleanup, and retaining previous outputs on extraction failure.
- **Failure/limitation:** An initial verification script compared rotated fixture boxes against its unrotated MediaBox and flagged a false error; checking pdfplumber's displayed dimensions confirmed the coordinates. Blank pages can legitimately yield empty OCR output and remain visible in the log. No WER, table accuracy, corrected multi-column order, or managed fallback is claimed. DVC/CI integration remains separate.
- **Confidence/responsibility:** High confidence in observed routing and box conversion; accuracy still needs P9 ground truth. Author must review, explain, modify, test, and defend the implementation.


## P1 local code review

- **Tool/model:** Codex (GPT-6). Reviewed OCR routing, coordinate conversion, manifest identity, output lifecycle, and assignment scope.
- **Finding/fix:** Removing a PDF from the input left its old text and word JSONL in the output while the log described only the new corpus. Reproduced this in a temporary directory. Successful runs now remove stale stage-owned files, including removed documents and obsolete page files, while preserving unrelated files. Cleanup follows successful extraction and output replacement.
- **Verification:** Temporary checks confirmed removed-document cleanup, shortened-document cleanup, unrelated-file retention, and exact 20-character / 30-percent decision boundaries. Existing repository suite: 16 passed. Fresh fixture run: all three scans used OCR with nonempty text; statement and multi-column fixtures remained native. No new permanent tests were added. `git diff --check` passed.
- **Limits/responsibility:** No further blocking P1 findings in this review. Accuracy still needs P9 ground truth; P2/P3 and DVC integration remain separate. Multi-file publication is not an atomic transaction against disk/process failure. Author review remains required; commits are local only pending explicit push approval.

## 2026-10-07 — Fix embedded images in filing PDFs

- **Tool/model:** Codex (GPT-6). Fixed P0 unpacking to decode uuencoded binary attachments and render from the original HTML under `unpacked/`, beside its relative image assets. Added a pre-PDF check that rejects unloaded/broken HTML images. No new dependencies or permanent tests were added.
- **Cause:** The prior unpacker wrote encoded ASCII into `.jpg` files, and the renderer opened `primary-document.html` one directory above the assets. The resulting broken-image icon and `g6614` text were already in the PDFs before P1 extraction. Earlier visual verification missed the defect; this entry corrects those completeness claims.
- **Verification:** Re-downloaded both pinned filings and regenerated their PDFs. Both logos and the 10-K stock-performance chart were visually verified. All three decoded JPEGs exactly match SEC's separately served originals (10,963 bytes per logo; 146,350 bytes for the chart). PDF page counts remain 61 and 30. Compared text page by page with backed-up PDFs: differences only on 10-K pages 1/23 and 10-Q page 1. Refreshed P1 outputs contain no `g6614` cover text. A temporary missing-logo check raised before PDF creation. Existing repository suite: 46 passed; git diff --check passed.
- **Failure/fix during verification:** SEC's final encoded line uses non-zero padding and blank separator lines. Matched standard uu-decoder padding handling and skipped blank separators; exact-byte comparison caught and eliminated 32 trailing zero bytes from an intermediate version. Full test collection initially lacked the already-pinned Camelot dependency locally; installed it under root requirements constraints before rerunning.
- **Limits/responsibility:** Verified on local macOS; Linux execution and downstream teammates' regenerated outputs remain unverified. PDFs/data are ignored by Git and must be regenerated or shared separately. Author review and ability to explain, modify, test, and defend these changes remain required.

## 2026-10-07 — P8: initial DVC pipeline (issue #35)

- **Tool/model:** Codex (GPT-6). Initialized DVC and added `download`, `render`, and `parse_pdfplumber` stages with script/shared-requirements dependencies, relevant parameter keys, and separate output directories. Generated `dvc.lock` from an actual run and documented local reproduction. Existing P0/P1 scripts and parameter values were unchanged; no new permanent tests or dependencies were added.
- **Verification:** First `dvc repro` executed all three stages and downloaded the pinned one 10-K and one 10-Q. Outputs contain 61/30 PDF pages, 91 page-text files, two word JSONL files, and 91 OCR log rows (90 native, one OCR). Second `dvc repro` skipped all three stages; `dvc status` reported up to date. A temporary change from `ocr.min_chars: 20` to `21` marked only `parse_pdfplumber` outdated; restoring the exact original params returned an empty JSON status. Existing suite: 46 passed. `git diff --check` passed.
- **What broke and how we fixed it:** Running DVC inside the restricted assistant sandbox could not open its local database; running with approved filesystem access resolved that environment restriction. The installed DVC rejects `dvc dag --ascii`; plain `dvc dag` displayed the expected three-stage chain. Neither required a source-code workaround.
- **Limits/review:** This branch is based on the still-open image-fix PR #102 so cached PDFs include corrected assets; merge that prerequisite first. Existing local stage outputs were backed up before reproduction. No S3 remote, CI, teammates' stages, clean-Linux reproduction, or cross-machine byte-identical PDFs is claimed. Author reviewed the local change and authorized committing, pushing, and PR creation after code review. Teammate review remains required.
- **Review:** Checked stage commands against the existing CLIs, imported code dependencies, parameter keys consumed by each script, output ownership, and lock-file consistency. Consolidated DVC local-state ignore rules into the root `.gitignore`. Removed trailing whitespace from generated YAML without changing its contents. No blocking code-review findings.
- **Confidence:** High for the measured local three-stage execution, unchanged-run skipping, and OCR-parameter dependency behavior.
