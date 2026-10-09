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

## 2026-10-07 — P8: fixture-only GitHub Actions (issue #36)

- **Tool/model:** Codex (GPT-6). Created `lokesh/p8-ci-smoke` from updated `main`. Added the PR smoke workflow, least-privilege checkout, a 15-minute timeout, cancellation of superseded runs, and pip caching. Official checkout/setup-python v6 actions are pinned to their resolved commit SHAs. Added a CI dependency subset constrained by shared requirements, usage documentation, and the case-study-required fixture extraction and pytest commands. No new permanent test files or pipeline scripts were added.
- **Verification:** Installed `requirements-ci.txt` into a fresh temporary Python 3.11 environment; `pip check` found no broken requirements. Executed the workflow's exact extraction, output-check, and pytest command blocks locally. Five fixture pages processed: three scanned pages used OCR with 3,620 / 1,194 / 2,759 characters; two native pages stayed native. Table extraction scanned five pages and wrote one statement table using Camelot stream. All smoke-output assertions passed; existing tests: 46 passed. One-off actionlint 1.7.12 validation passed; the linter was kept outside the repository.
- **Failure/limitation:** Docker access was unavailable inside the assistant sandbox, so this was a clean macOS Python-environment check, not an Ubuntu runner execution. Package/system installation needs network access, but extraction and tests use local fixtures and mocks. The final workflow was narrowed to Part 8 requirement 4 (page 11): removed the extra inline output assertions, pip check, and main/manual triggers. Earlier output assertions and pip check results above are one-off local evidence, not recurring CI steps. A green GitHub Actions run remains unverified until the author approves pushing and opening a PR; no remote run or branch-protection enforcement is claimed.
- **Confidence:** High for the checked workflow syntax, dependency subset, and local fixture/test results; Ubuntu execution awaits the actual PR check.
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

## CI collection fix after teammate merges

- **Cause:** New export, Docling, and layout tests were merged after the initial 46-test CI run. Export tests need Pydantic; Docling/layout helper tests were importing model packages at module load even though they do not execute inference.
- **Change:** Added Pydantic to the CI subset using the shared version constraint. Moved Docling imports and its package-name collision workaround into `make_converter`, restoring `sys.path` even on import failure. Docling version metadata is read when exporting blocks. Moved PyTorch/LayoutParser setup into model/detection functions; model-free table routing remains available without those packages. Existing tests are unchanged; no new tests or recurring CI steps were added.
- **Verification:** Updated the temporary CI environment, which has neither Docling nor PyTorch installed. Full existing suite: 91 passed, 1 skipped (the existing export integration test requires local generated data). Workflow lint and diff whitespace checks pass. An initial local attempt exposed the file-loaded Docling test's dependency on adding `src` to `sys.path`; retained that existing behavior for sibling imports.
- **Limits:** Actual model conversion/detection was not rerun; it still requires the full root requirements and model weights. These changes remain local pending author review and push approval; a new remote CI result is not claimed.

## 2026-10-08 — Part 8 stage integration (#46), draft for author review

- **Tool/model:** OpenAI Codex (GPT-6).
- **Contribution:** Added tables, layout, parse_docling and export to DVC on main d7fcffd. Tracked shared table code, rendered inputs and Docling's original-HTML dependency. Export invokes the existing TXT writer so one stage produces all three formats. Existing QA images remain Git-tracked in reports/layout; figure crops are DVC outputs.
- **Verification:** `dvc dag` successfully resolved the seven-stage graph. Existing `pytest -q`: 91 passed, 1 skipped. No new recurring tests or dependencies added.
- **Failure/limitation:** DVC initially could not open its database in the sandbox; approved local access resolved it. Full reproduction and dvc.lock generation are deferred to the evening run at the user's request. #47 cannot be completed until Guna supplies the managed module and its return/cache contract; no speculative adapter was added.
- **Confidence:** Graph structure and existing regressions checked; end-to-end completion remains unverified until the scheduled reproduction.

### Full local reproduction verified before push

- Activated the project virtual environment and installed the existing pinned requirements. An initial run used the shell's unrelated Python and stopped at missing pdfplumber; the activated environment initially lacked model packages. Neither failure required source changes.
- Completed all seven stages through export on the 61-page 10-K and 30-page 10-Q. Traditional table extraction wrote 32 tables. Layout reported no missed nonblank pages. A second `dvc repro` skipped all seven stages; `dvc status` reported up to date.
- Validated every JSONL: traditional 497/248 records and Docling 603/263 records for 10-K/10-Q, respectively; 1,611 total with zero validation errors. Nonempty JSONL, Markdown and TXT exist for each filing. Full existing suite now passes all 92 tests, including the formerly skipped export integration test.
- Committed generated dvc.lock. Regenerated QA images were backed up under /tmp/lantern-p8-layout-qa and excluded from the integration diff. Generated artifacts remain in the local DVC cache; no remote artifact push or EC2 reproduction is claimed. Schema validity does not establish extraction accuracy. #47 remains pending the managed module.

## EC2 reproduction and S3 DVC remote

- Environment: Ubuntu 24.04.4 LTS, x86_64, m7i-flex.large, Python 3.11, PyTorch 2.14.1+cpu; Chromium launch verified.
- Configured lantern-s3 at s3://lantern-team2-dvc-fall-2026/dvc in us-east-1. Authentication uses the attached LanternEC2Role, without stored AWS access keys.
- All seven DVC stages completed across the 61-page 10-K and 30-page 10-Q. Second reproduction skipped every stage; DVC reported up to date.
- Existing tests: 94 passed in 3.54 seconds.
- Upload: 593 files pushed; DVC confirmed the local cache and S3 remote are synchronized.
- Failures resolved: pinned Playwright could not install on Ubuntu 26.04, so the instance was replaced with Ubuntu 24.04. CUDA dependency downloads hit a storage limit; CPU-only PyTorch and a disk-backed temporary directory resolved installation.
- Limitations: Linux output hashes differ from the earlier Mac run. Grader access and retrieval from an empty cache remain unverified.
- AI assistance: OpenAI Codex guided setup and troubleshooting; commands were run manually on EC2.

## 2026-10-08 — #66 README update (draft for author review)

- **Tool/model:** OpenAI Codex (GPT-6).
- **Contribution:** Replaced the initial three-stage README with the current ten-stage architecture, repository tree, Linux/Python 3.11 and CPU setup, private S3/IAM-role access, reproduction and fixture commands, app launch, benchmark-based runtime guidance, all Parts and report links, contribution allocation, AI disclosure, and the exact Section 8.2 attestation. Created a separate branch from main ac01916. The four 25% shares follow issue #66; authors must review the declaration before submission.
- **Verification:** Cross-checked commands and paths against dvc.yaml, params.yaml, requirements.txt, smoke.yml, app/app.py, reports/benchmarks.md, and existing engineering logs. Read the local case-study brief's Sections 7–8.2 for reproduction and verbatim attestation. Checked local Markdown targets, paired fences, all ten stage names, attestation text, and git diff whitespace. No pipeline runs or new runtime results are claimed for this documentation change.
- **Failure/limitation:** Initial link validation caught the missing tests/fixtures/README.md; replaced those links with the existing fixture directory. Final Codelab/video/app links, the submission tag, and current full EC2 reproduction evidence are unavailable and explicitly pending. PR #125 is described as pending rather than already merged. Issue #66 must remain open until final links and evidence are filled in. No application tests were rerun for prose-only changes.
- **Confidence:** Documentation matches inspected main and recorded evidence; final publication readiness remains conditional on the listed deliverables.
## 2026-10-08 — #47 managed OCR fallback and DVC inputs (draft for author review)

- **Tool/model:** OpenAI Codex (GPT-6).
- **Contribution:** Branched from main ac01916. Added low-confidence Tesseract escalation using the existing Textract cache/API path. Converted the 0–100 OCR confidence to the configured 0–1 threshold; empty OCR also triggers a check. Cached or live Textract WORD boxes retain point coordinates and confidence. Disabled cache misses and empty responses retain Tesseract with explicit log status; service/cache errors propagate. Existing two-argument parser callers remain local-only. Added managed code/config/cache dependencies to the parsing stage, tracked evaluation's managed settings, and made parsing/tables/evaluation follow managed.cache_dir.
- **Verification:** Temporary checks passed for disabled misses and hits, threshold boundary, empty OCR, word boxes, page routing, empty responses, error propagation, and mocked API/cache reuse. An isolated DVC parsing stage processed all three scanned fixture pages with managed.enabled=false and min_ocr_conf=1.0 (to exercise the miss path); the second repro skipped and status was up to date. No cloud OCR calls were made. Full existing suite: 166 passed, 1 skipped, 5 failed. Running the affected export/quality tests on unchanged main with the same local artifacts reproduced all five failures (38 passed).
- **Failure/limitation:** Existing local exports fail current schema, quarter, prose CER, table coverage, and bbox checks. These artifacts need the scheduled full reproduction; this change does not claim to fix their quality. DVC initially hit a sandbox restriction on its system cache; the approved rerun passed. Full ten-stage reproduction and root dvc.lock regeneration remain deferred until the managed cache is available and final EC2 integration runs. Live Textract was not exercised. Temporary checks were not added to recurring CI.
- **Confidence:** Local fallback behavior and isolated disabled-mode DVC execution verified; final artifact quality and full graph reproduction remain pending.

### PR #125 review follow-up — 2026-10-09

- Addressed Guna's requested persistent regression coverage: disabled cache miss preserves Tesseract, cached managed text/word boxes replace it, 0–100 confidence threshold boundaries and empty OCR, and empty managed responses preserve local OCR. Tests explicitly forbid AWS calls. These recurring checks were requested in review and authorized by Lokesh's request to address the comments.
- Standardized the OCR log engine to `aws-textract`, matching the managed records' extractor label.
- Validation: targeted parser and managed fallback/config suites passed (see review follow-up results). Full integrated EC2 reproduction remains pending; Guna's separate fixture-quality isolation follow-up is not implemented here.

## 2026-10-09 — portable benchmark device selection

- **Tool/model:** OpenAI Codex (GPT-6).
- **Contribution:** Added availability checks for MPS/CUDA benchmark jobs, explicit skipped.json evidence, cleanup of stale unavailable-device outputs, current-run summary scope, and empty-summary handling. Excluded stages with errors or zero pages from cost projections and replaced hard-coded Mac labels with measurement-host labels. Existing Mac report results are preserved and distinguished from later runs. DVC already tracks src/bench.py and the whole data/bench output directory, so no dependency change is needed.
- **Verification:** Existing benchmark tests: 2 passed. Temporary mocked checks verified unavailable MPS never launches a subprocess, stale MPS output is removed, an all-skipped run writes an empty summary, a failed 94-page MPS result is excluded from costs, and successful CPU results remain. git diff --check passed. No new recurring tests added.
- **Failure/limitation:** The EC2 run previously treated 94 failed MPS attempts as fast processing and generated invalid GPU cost estimates. This patch does not regenerate EC2 artifacts; rerun only the bench stage there after integration. VM projections still depend on declared worker/hardware assumptions; zero local-host compute charges are not a claim of free EC2 hosting.
- **Confidence:** Device routing and cost exclusion verified without model downloads; full corrected benchmark timings require the EC2 rerun.

### PR #128 review follow-up — preserve benchmark evidence

- Guna identified that deleting stale MPS files could remove the Mac CSV evidence still quoted in the report. Added a content-addressed archive of all existing top-level benchmark CSV/JSON files before main() modifies outputs, including machine metadata, summaries, and costs. Archives remain within the DVC-managed data/bench directory and are excluded from current-run aggregation.
- Added the review-requested persistent tests for unavailable-device subprocess prevention, byte-for-byte preservation, all-skipped empty summaries, and failed/zero-page cost exclusion with successful CPU retention. Existing and new benchmark tests: 4 passed; git diff --check passed.
- Limitation: this preserves available prior files, not evidence absent from EC2. The original Mac bundle must still be obtained from its author if it was never transferred. No regenerated EC2 artifacts or recovered Mac data are claimed.

### EC2-only reporting follow-up

- At Lokesh's request, replaced the Mac/MPS benchmark comparisons with the successful EC2 CPU observations supplied in this conversation. Added reports/ec2_benchmark_observed.csv as an explicitly labeled transcription of those terminal summary rows; it is not claimed as a downloaded/generated artifact.
- Removed unsupported GPU cost/performance conclusions. Cost formulas and configured assumptions remain documented; final numeric cost rows and report refresh await the corrected EC2 rerun. Original Mac data is no longer required to support this report's measurements.
- Verification: checked the four report rows against the transcribed CSV and original supplied CPU summaries; CSV error counts are zero, each has 94 pages. git diff --check passed. No new execution or final S3 upload claimed.

### Final EC2 reproduction validation
- Reproduced the pipeline on Ubuntu 24.04 EC2 using CPU execution.
- Validation: 183 tests passed; DVC reports data and pipelines up to date.
- Uploaded generated DVC objects to S3; cache and remote are in sync.
- MPS was explicitly skipped because it is unavailable on this host.
- GPU cost estimates were omitted because no successful GPU measurement exists.
- Recorded regenerated metrics, bounding-box fallback evidence, layout previews,
  and drift plot. Metrics include both improvements and regressions.

### Streamlit deployment README and review handoff
- Tool: OpenAI Codex. Updated the README with the Elastic IP app URL, systemd operations, overnight stop/start behavior, and the completed reproduction status.
- Evidence: Lokesh confirmed the public app worked and supplied a health-check response of `ok`; reproduction and S3 validation are recorded above. These are user-run EC2 checks, not a new remote execution by Codex.
- Integrated main through PR #129 without changing the teammate reports. The earlier 183-test run predates that fixture-test update.
- Limitation: final fresh-cache retrieval and benchmark-report refresh remain pending; HTTP availability requires EC2 to be running. No TLS or continuous uptime is claimed.
- Verification: reviewed the documentation diff and ran git diff --check. No application or pipeline code changed in this documentation update.
- Confidence: high for the documented user-verified deployment; final release validation remains explicit.


### Final EC2 benchmark report refresh — October 9, 2026
- Tool: Codex. Retrieved final benchmark CSV/JSON artifacts over SSH from the deployed EC2 checkout and updated the observation CSV, report, and README status.
- Verification: observation CSV matches every field of the retrieved summary (line endings normalized); all four stages cover 94 pages with zero errors. Final means are 0.293 / 0.540 / 1.021 / 6.503 seconds per page. Cost projections were copied from the accompanying cost.csv; MPS is explicitly skipped.
- Limitation: local DVC retrieval returned S3 403. The original EC2 checkout lacked the outputs; the deployed checkout contained them. No benchmark rerun or fresh S3 retrieval is claimed. Cost projections retain unmeasured four-worker scaling and different VM hardware assumptions.
- Confidence: high for transcription of retrieved evidence; cost projections remain assumptions. Author review pending.

### P0 fixture provenance follow-up — October 9, 2026
- Tool: OpenAI Codex. Created `lokesh/p0-fixture-provenance` from updated main `8f5504c` at Lokesh's request. Added `tests/fixtures/README.md` and linked it from the Part-to-file map. Documented source accessions/URLs, page selections, rasterization settings, native-page extraction, fixture hashes, and current ground-truth coverage. Recovered historical preparation details from commit `51bcc8d`; no fixture PDFs or pipeline code changed.
- Verification: checked all three SHA-256 values, byte counts, page counts, text-layer presence, and relative documentation links against local files. Existing fixture quality tests: 5 passed. Used the existing Python 3.11 environment with the previously installed temporary jiwer dependency via PYTHONPATH. `git diff --check` passed. No new persistent tests were added.
- Failure/limitation: the historical README referenced a removed builder and tests; this update describes them as historical, not runnable current commands. Only scanned page 1 has a committed transcription. No new external-source download, full Linux reproduction, or S3 retrieval was performed. Prior full-suite review found 5 failures against stale local corpus outputs; passing fixture tests do not certify those outputs.
- Confidence: high for fixture provenance recovered from preparation history and checked artifact structure; final integrated artifacts remain subject to EC2 validation. Draft AI Engineering Log for the author's review before any PR.
