# Lokesh AI Engineering Log

## Issue #11 — Python 3.11 environment

- Tool: Codex (GPT-6). Created the isolated environment, pinned its dependencies, and drafted setup documentation.
- Verification: `pip check` passed; P0 scripts and P1/P8 package imports passed; Chromium rendered a synthetic page, pdfplumber extracted its text, Poppler rasterized it, Tesseract recognized `LANTERN 12345`, and img2pdf produced a readable one-page image-only PDF. DVC and pytest version commands passed.
- Changes: selected installed Python 3.11.11 explicitly instead of the shell's Python 3.14; reused installed Tesseract, Poppler, and Chromium; retained the four dependency versions already pinned by PR #88. Added tools for the assigned P0/P1/P8 scope and froze resolved dependencies.
- Limitation: verified on macOS arm64 only; no Linux clean-room run, cloud access, DVC pipeline run, or project tests were claimed. Existing P0 scripts were imported from the original checkout, since they are not merged into main. No data downloads or cloud services were invoked.
- Confidence: high for the observed local setup; cross-platform and full-pipeline reproduction remain unverified. Author must review this entry and be able to explain, modify, test, and defend the changes before submission.
