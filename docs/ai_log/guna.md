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

## Part 9: ground truth (data/ground_truth/, tests/fixtures/gt/)

- Tool/model: Claude (Opus) in claude.ai chat, used for planning and for the conventions document. Not used for transcription.
- What it contributed: Discussed the stratified sample and the transcription conventions with me before any page was typed. Drafted CONVENTIONS.md from rules I set, and the reshaping script scripts/write_gt_tables.py, which turns my keyed grid into one line per cell. It did not read, transcribe or check any page: every one of the 18 pages and both statement tables were keyed by me from the 150 DPI page images. It declined to verify my transcription against the images, on the grounds that the double-keying with a second person (#27) is the independent check and a model reading the page would be the same category of thing being measured.
- How verified: Both tables checked arithmetically independent of the parser and of the tool. 10-K p32 reconciles in all three years from net sales through to net income, and net income divided by each share count gives the printed EPS to the cent in all six cases. 10-Q p6 balances in both periods with every subtotal adding up.
- Changes: The conventions were written before transcription. Three rules were added during it and are marked as such in the file: the section prefix on repeated row labels (four labels on p32 and two on p6 appear twice on the page), the per-row scale (p32 is headed "In millions, except number of shares, which are reflected in thousands, and per-share amounts"), and the [unreadable] marker for logo text.
- Failure/limitation: Excel silently corrupted the first table CSV. Opening and saving it rewrote the value column in scientific notation rounded to three significant figures, so 307003000000 became 307000000000 and table cell F1 came out at exactly 0.0 with no error. Caught because the 10-Q table scored 1.0 on the same pipeline, which made a reading failure implausible. Now guarded by test_ground_truth_values_are_full_precision. Separately, four of my text files retain the page footer against my own rule; found while scoring and recorded in the conventions rather than silently fixed after the numbers were seen. Single transcriber except the two tables.
- Confidence: High that the ground truth was produced independently of any parser output, which is the property that makes it worth anything. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 9: evaluation, quality gates and drift (src/evaluate.py, tests/test_quality.py, reports/)

- Tool/model: Claude (Opus) in claude.ai chat. I ran every command and checked each output before the next step.
- What it contributed: Wrote src/evaluate.py, tests/test_quality.py and the first draft of reports/eval.md. Proposed reporting per stratum rather than as one average, and the --break modes for proving the gates have teeth.
- How verified: Ran the evaluation, pasted the output back and inspected it at each step. Prose WER 0.043 to 0.153; table cell F1 1.0 on both tables (57/57, 56/56); statement numeric-token F1 0.954. Teeth: --break no-scale drops table cell F1 to 0.105 and 0.000, and the recorded run shows two gates failing with 0.1053 >= 0.9. 115 tests passing.
- Changes: The first version scored a statement page as a whole page of reference text against only its headings, because table content is routed to the tables stage. Fixed by folding table rows into the page hypothesis as tab-separated lines, the same convention the reference uses; numeric-token F1 went from 0.315 to 0.750. Kept page-level WER for prose and reported numeric-token and cell F1 as the headline for table strata, rather than tuning WER until statement pages looked good.
- Failure/limitation: The tool wrongly concluded at one point that the export file had been edited between two runs, from row labels like "Net sales: Products" that it believed the parser could not produce. The pattern came from Part 2's normalisation; the real cause of the 0.0 score was the Excel corruption above. The text gates are loose and have never been observed to fire: prose WER is gated at 0.25 against a measured 0.153 and neither break mode damages prose. Docling table cell F1 is not reported because the Docling export is text-only. dvc repro evaluate and dvc metrics diff are blocked on the evaluate stage, handed to Part 8.
- Confidence: High that each metric is computed as described and applied identically to both sides. Medium on generalisation: one company, two filings, two tables. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 5: table bbox fallback, second review (src/export.py, tests/test_exports_bbox.py)

- Tool/model: Claude (Opus) in claude.ai chat. The bug was in code it drafted for me, and the corrected version was caught by a teammate, not by me or the tool.
- What it contributed: The original fallback for a table on a page with no layout Table region was a constant [0, 0, 1, 1]; the Part 9 metric surfaced it on 10-Q p6 and p9. Its first replacement used the union of every layout block on the page. Lokesh's review on #110 showed that on a page whose only detection is a heading, the union is the heading's box, so the table was exported pointing at the wrong region. The union is correct only when every box in it is a Table detection, and it had been reused from that case without rechecking.
- How verified: The bbox choice is now one function returning the box and a precision label, detected / union / page, covered by tests for all three branches including the heading-only page from review. Every approximate box is logged to reports/export_bbox_fallback.csv: 11 of 55 tables, 8 unions and 3 full pages (10-Q p6, p9, p28). An earlier diagnostic that looked only at sampled pages had found two of the three. Re-running the evaluation moved no metric. 115 tests passing.
- Changes: The no-detection case uses the real page box read from the rendered PDF rather than any detected block. #110 closed in favour of the Part 9 PR, which carries the fix rebased onto current main.
- Failure/limitation: A full-page box is truthful but imprecise. The real fix is a bbox column in the Part 2 output, raised with the owner. Nothing in the schema can catch a wrong bbox, so it has to be recorded where the approximation is made.
- Confidence: High that no table record now carries another region's box. Medium on precision for the 11 logged records. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 5: extractor_version on text blocks (src/adapters.py)

- Tool/model: Claude (Opus) in claude.ai chat, which had written the original line.
- What it contributed: Diagnosed that text blocks reported extractor pdfplumber with extractor_version lp://efficientdet/PubLayNet/tf_efficientdet_d0. The layout record supplies extractor_version null and a separate model field, and the adapter fell back to model: a version string for a different tool.
- How verified: Text blocks now report pdfplumber 0.11.10, looked up from the installed package the same way the table-side fix does. Record counts unchanged at 497 and 252.
- Changes: One line in block_from_layout_record. Prefers the stage's own extractor_version if Part 3 ever populates it.
- Failure/limitation: The analogous table-side bug was found in review a day earlier and the text side was not checked at the same time.
- Confidence: High. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 7: Textract module, cache and side-by-side (src/managed/textract.py, data/managed/)

- Tool/model: Claude (Opus) in claude.ai chat. I ran every command, made the 3 paid API calls myself, and checked each output before the next step.
- What it contributed: Wrote the Textract module (render the page with pdftoppm, cache by sha256 of the page image, map Textract's block graph into the Appendix B schema), the raw cell F1 metric so Textract is scored on reading and not on scale normalisation it never does, and the first draft of reports/build_vs_buy.md. Looked up the pricing and data-privacy terms on aws.amazon.com and quoted them with the date.
- How verified: 3 pages sent (10-K p32, 10-Q p6, scanned fixture), 30 schema-valid records. Every re-run after that came from cache, no second paid call. Scored against my hand-keyed ground truth: raw cell F1 1.0 on both tables.
- Changes: The tool first told me the cost was $0.025 per page, adding a $10/1k Layout charge. That was wrong, the AWS pricing page says Layout is free with Tables, so it is $0.015. Corrected in the report. It also first explained the big WER gap between paths as "the table is one block plus section prefixes". The Docling comparison later proved that wrong: the real cause is the layout Table box covering only the number columns (eval.md finding 6). The report now says this openly.
- Failure/limitation: Only 3 pages and one provider. The scanned page is a clean scan, so harder scans were not tested.
- Confidence: High on the numbers, they are measured and re-run in CI. Medium on how far they generalise. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 7: fallback inside the tables stage, DVC tracking, review fixes on #116 (src/tables.py, src/export.py, dvc.yaml, tests/)

- Tool/model: Claude (Opus) in claude.ai chat. Dhruvi owns src/tables.py, I asked her before changing it. dvc.yaml is Lokesh's file, I told him what I added.
- What it contributed: Wrote managed_fallback() in tables.py and its tests, the dvc add data/managed step and the new deps on the tables and evaluate stages, and after review on #116 the three fixes: the managed table now replaces the low-score Part 2 table in the export (logged in reports/export_managed_tables.csv), textract.py takes the caller's params and reads no params file on import, boto3 is pinned and the real error is kept in a fallback_error column.
- How verified: Full tables stage after the change: same 32 tables, same winners. dvc repro -s tables with managed.enabled: false runs clean. Mocked tests prove no API call when the passed config says enabled: false, even if another params file says true, also through the real boundary tables.managed_fallback() into the real module. A forced low-score page with a cache hit changes the export and ends with exactly one table. 151 tests passing.
- Changes: The first trigger rule fired on 45 of 91 pages. I checked the log: all 45 had score 0.0 and no numeric rows, they were pages with no table at all. Fixed by asking for 3 numeric rows, now 0 of 91 trigger, and a regression test guards it. The first version of the fallback also never reached the export and ignored the caller's config. I did not catch these two myself, the reviewer on #116 did.
- Failure/limitation: dvc push of data/managed gives 403 on the team bucket, waiting for access from the Part 8 owner. Until then a fresh clone cant dvc pull the cache. Only the table side of the trigger is wired, the OCR side in parse_text.py (#47) is separate work.
- Confidence: High that the fallback is off by default, never fails the stage, and never duplicates a table. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 9: review fixes on #111 and fixture gates in CI (src/evaluate.py, tests/, params.yaml, reports/eval.md)

- Tool/model: Claude (Opus) in claude.ai chat. Every point came from reviews on #111 and from Shravya's comment, not from me or the tool.
- What it contributed: Wrote the fixes and their tests: lost pages scored as empty and listed as missing (not skipped), quality gates that run evaluate.py fresh instead of reading the committed metrics.json, Counter matching so repeated numbers count, html.unescape before scoring, fixture gates that score the outputs the CI smoke job already makes, the drop-words break mode for the text gates, the evaluate stage in dvc.yaml with the metrics diff evidence, and the double-keying reconciliation files (#27). It also rewrote both reports in simpler English on my request, numbers and terms unchanged.
- How verified: Each review case is a test with the reviewer's own example (two pages with output for one, 100 100 100 vs 100, &amp;). drop-words makes both prose gates fail and nothing else. dvc metrics diff shows only the table scores moving under no-scale. Fixture results in CI: scanned WER 0.0225 (Tesseract), statement WER 0.0714, statement table cell F1 1.0, multicolumn WER 0.9255. 133 tests passing. Double-keying: 113 cells compared, 0 value disagreements.
- Changes: Counting repeats lowered numeric F1 (traditional 0.7497 to 0.7235, 10-Q p6 traditional 0.9412 to 0.8467). The report uses the new numbers everywhere and says why. This also supersedes the limitations in my earlier Part 9 entry: text gates are proven now, Docling table F1 is reported, dvc repro evaluate and dvc metrics diff work.
- Failure/limitation: My first push of the new tests broke CI, because requirements-ci.txt had no jiwer. Fixed. Multicolumn raw text is bad (finding 10), the gate only stops it getting worse. Ground truth stays in git and not DVC, because there is no remote access yet and moving it would leave everyone else without it.
- Confidence: High that every metric is computed the same way on both sides and that the gates fail on real damage. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 5: Docling tables in the export (src/export.py, src/adapters.py)

- Tool/model: Claude (Opus) in claude.ai chat. The bug was found by Shravya in review on #111, not by me or the tool.
- What it contributed: My export skipped every Docling Table record and never read data/docling/tables/. The tool changed the export to read the Docling table CSVs with the same function that reads Part 2's, so both paths reach the schema the same way.
- How verified: 54 Docling tables now in the export. Docling cell F1 1.0 on both ground truth tables (57/57, 56/56), numeric F1 0.345 to 0.851. Traditional numbers did not move, so the change only added the missing tables. I also checked the WER gap with a block-by-block look at 10-K p32, which is how finding 6 was found.
- Changes: My earlier finding blamed Docling for having no tables. That was wrong, it was my export. Rewritten in eval.md finding 3 with credit to Shravya.
- Failure/limitation: 6 of the 54 Docling tables have a union bbox, logged like the traditional ones.
- Confidence: High. I have reviewed this entry and can explain, rerun and defend every step of it.

## Part 1 and Part 4: UTF-8 file encoding (src/parse_text.py, src/docling_parse.py)

- Tool/model: Claude (Opus) in claude.ai chat. Both files belong to teammates, Lokesh and Shravya agreed before I changed them, and they reviewed the PR.
- What it contributed: Listed every text read and write without encoding="utf-8" (9 lines) and wrote a one-time script that changed exactly those lines, only if each matched once, keeping the line endings so the diff was 9 lines.
- How verified: git diff showed 9 insertions and 9 deletions in 2 files. Tests passed. Later the same bug showed up live while I measured the fixtures on Windows (a cp1252 apostrophe in the OCR output), and after the PR merged it was gone.
- Failure/limitation: Only these two files were checked, other files were not audited.
- Confidence: High. I have reviewed this entry and can explain, rerun and defend every step of it.