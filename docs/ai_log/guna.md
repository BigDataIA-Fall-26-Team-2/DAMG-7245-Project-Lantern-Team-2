# Sai Guna Vardhan Vudatala AI Engineering Log

## Part 5  normalized block schema (src/schema.py)

- Tool/model: Claude (Opus 5) in claude.ai chat, used as a step-by-step guide. I ran every command myself and checked each output before the next step.
- What it contributed: Discussed the Appendix B field list with me and which constraints belong in validators rather than in calling code. I decided which failure modes to guard and reviewed every validator before keeping it; it drafted this entry.
- How verified: Hand-fed malformed records and confirmed each validator fires by name, then automated it as `tests/test_export.py`, 16 tests, all passing. `validate_jsonl` on the 10-K export: 497 records pass, 0 errors. A record with doc_id "bad" and missing fields is rejected with 16 named field errors.
- Changes: Used `extra="forbid"` so unknown upstream fields are rejected loudly rather than silently carried. Required `bottom > top` on the bbox, which rejects an unflipped bottom-left box at the boundary instead of letting it through.
- Failure/limitation: The field name `schema` collides with a Pydantic BaseModel method, so the model field is `schema_version` with `schema` as an alias and dumps use `by_alias=True`; this was not obvious until it failed. The schema checks form, not truth: a record on the wrong page with the wrong text is still valid. Correctness is measured in Part 9, not here.
- Confidence: High that every emitted record satisfies the contract. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 5  export rewritten to read stage outputs (src/adapters.py, src/export.py)

- Tool/model: Claude (Opus 5) in claude.ai chat, used as a step-by-step guide. I ran every command myself and checked each output before the next step.
- What it contributed: Drafted the rewrite of `src/adapters.py` and `src/export.py`. The direction came from me: after running all four upstream stages locally I questioned why export was calling the libraries again when the stage outputs were already on disk, and I inspected the real field names before any code was written against them.
- How verified: Ran P0 download and render, P1 text, P2 tables, P3 layout and P4 Docling end to end on the two pinned filings, then inspected `data/layout/*.blocks.jsonl`, `data/docling/*.blocks.jsonl`, `data/rendered/manifest.csv` and `data/tables/*.csv` field by field before writing against them. Export output: 10-K traditional 497, docling 605; 10-Q traditional 252, docling 265. The params.yaml refactor was verified by re-running and confirming the four counts were unchanged.
- Changes: The earlier version called pdfplumber, Camelot and Docling live inside export. That duplicated upstream work and created a second source of truth different from what the team commits. Export now reads files only, so there is one source of truth per stage. Moved the output paths, paragraph gap, Docling toggle and ticker-to-company map into a `params.yaml` `export` section.
- Failure/limitation: P3 Table blocks mostly carry `table: null`, so table content comes from the P2 CSVs; on 10-Q page 2 P3 detected a full-width Table at score 0.338 (the table of contents) and the P2 extractor correctly refused it, `accepted: false`. `fiscal_year` and `fiscal_period` are derived from the manifest period string, not dei facts, so the 10-Q is labelled "Q" rather than a specific quarter. `company` is derived from ticker until the render manifest carries a company column.
- Confidence: High that the output is schema-valid. Not yet confident it is correct; correctness is measured in Part 9. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 5  table bbox pairing bug

- Tool/model: Claude (Opus 5) in claude.ai chat. The bug was in code it had drafted for me, on an assumption neither of us had checked.
- What it contributed: Wrote the original single-bbox-per-page lookup, assuming one table per page because every P2 CSV filename ends in `_t1`, an assumption taken from the P2 output without checking the P3 side. The bug surfaced when I questioned why the known gaps were being carried into review instead of closed, and asked for each one to be justified.
- How verified: Counted P3 Table blocks per page: six pages of the 10-K have two (27, 31, 39, 42, 44, 45), while P2 wrote one CSV for each of those pages. Confirmed the fix on page 27, which now carries a union bbox `[216.2, 94.73, 552.55, 575.61]` spanning both detections instead of only the second. Re-ran the export: counts unchanged at 497/252. Full suite: 16 passed.
- Changes: The lookup now keeps every Table bbox per page in order instead of overwriting. Where P2 and P3 agree on the table count, boxes are paired in order. Where they disagree, the record carries the union box covering all detections on that page: deliberately wider rather than confidently wrong, because the bbox is the provenance claim.
- Failure/limitation: The union box is less precise than a true per-table box. The real fix is a bbox column in the P2 output or its log, which I have raised. Nothing would have caught this automatically: a wrong bbox is still a valid bbox, so the schema cannot detect it.
- Confidence: High that no record now silently carries another table's box. Medium on precision for the six affected pages. I have reviewed this entry and can explain, rerun and defend every step of it.

## Running the upstream stages on Windows

- Tool/model: Claude (Opus 5) in claude.ai chat, used for diagnosis. I ran every stage myself.
- What it contributed: Helped read the tracebacks and name the cause once I hit each failure. I found all three by running the stages on Windows; no one else on the team is on Windows, so none of them appear on macOS.
- How verified: Ran each stage end to end after each fix, on both pinned filings. P1 completed 91 pages; P2 reported 91 pages scanned, 32 tables, camelot-stream 17 and pdfplumber-text 15; P3 reported 61 and 30 pages with no missed pages; P4 took 141.0 s and 79.6 s and found 48 tables from the rendered 10-K PDF against 62 from the original HTML.
- Failure/limitation: Three unencoded writes in `src/parse_text.py` and five in `src/docling_parse.py` inherit cp1252 on Windows and crash on U+2612 from the SEC cover page. Poppler and Tesseract are system dependencies not installed by pip and are not in the README or CI. Also observed: P1 triggers OCR on 10-Q page 7, which P1's own acceptance criteria say should not happen on a rendered page, and P3 independently flags the same page blank. All reported to the owners; none fixed in this branch, since they are not my files.
- Confidence: High that these reproduce on Windows with the pinned versions. I have reviewed this entry and can explain, rerun and defend every step of it.