# AI Engineering Log — Lokesh

## 2026-10-03 — Issue #4: params.yaml skeleton

- **Tool/model:** Claude Code (Sonnet 5)
- **What it contributed:** Read Case Study 1 Appendix A (minimum `params.yaml` keys) to build the skeleton's 10 sections (one per owner/stage). When the plan changed from "two 10-Ks" to "one 10-K, one 10-Q," it found the tutorial's own worked example (`ticker/forms/after/before` block in the Tool Tutorial PDF) and pinned the actual filings by querying SEC EDGAR's `data.sec.gov/submissions` API directly for Apple's real accession numbers and period dates, then updated `params.yaml` and issue #5 (`docs/CONTRACTS.md`) to match.
- **How verified:** Parsed the generated `params.yaml` with `python3 -c "import yaml"` to confirm valid YAML and the exact key names from Appendix A; cross-checked the pinned 10-K/10-Q dates and accessions against SEC EDGAR's raw submissions JSON (not a summarized fetch — see limitation below).
- **Failure/limitation found:** A first attempt to look up Apple's most recent 10-Q via a web-fetch summarization tool returned an incorrect period date. Caught by re-fetching the raw EDGAR JSON and parsing filing dates/forms directly instead of trusting the summary.
- **Confidence statement:** High confidence in the 6 Appendix-A-mandated sections (`download`, `render`, `ocr`, `tables`, `layout`, `managed`). The other 4 sections (`xbrl`, `docling`, `bench`, `evaluate`) are intentionally left empty — the brief doesn't mandate keys for them, and their real values depend on work not yet done (Parts 4, 9, 10, 11).
