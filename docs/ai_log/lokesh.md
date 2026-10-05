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

- **Tool/model:** Codex (GPT-6). Selected source pages, built three Git-tracked PDFs, documented their provenance and added offline artifact checks. A temporary rebuild script was removed at the author’s request; fixture generation is a one-time preparation step, not part of the pipeline.
- **Verification:** Inspected all five output pages visually; scanned PDF has three image-only pages, statement PDF retains its text layer, and Amdocs PDF has four prose columns across an original spread. Full repository suite: 13 passed. A second build produced byte-identical PDFs. Final scan rendering matches the visually inspected version pixel-for-pixel. Total fixture size: 1,817,188 bytes.
- **Failure/fix:** Default img2pdf backend changed bytes between runs despite date suppression; explicitly selecting the internal backend fixed this. Full test collection initially failed because the local environment lacked the already-pinned pandas dependency; installed it under root requirements constraints, then reran successfully.
- **Limits:** External multi-column page is an SEC-filed Amdocs annual-report exhibit, not an Apple corpus document. Scans are clean rasterizations, not degraded real-world scans. No OCR accuracy or P9 ground-truth completeness is claimed; Linux execution remains unverified.
- **Confidence/responsibility:** High confidence in fixture structure, documented provenance, and measured checks. Author review and ability to explain, modify, test, and defend the deliverables remain required.
