# Storage format decision (Part 6)

**Decision: the Part 5 JSONL is the source of truth and is what feeds Case Study 2; Markdown is the human-readable view; TXT is a baseline only.** JSONL is the only format in which every record carries its page and bounding box, which is what traceable answers need. One condition: the JSONL must carry the tables. The Docling JSONL measured here is text-only (export skips Table blocks), and it could answer none of the three questions.

Document: Apple FY2025 10-K (`AAPL_10K_20250927`, 61 pages). Measurements: `reports/format_stats.csv`, from
`python src/format_stats.py --output reports/format_stats.csv md=… jsonl=… json=… txt=…`.

## Formats compared

| Format | File | Produced by |
|---|---|---|
| TXT | `data/export/AAPL_10K_20250927.txt` | `src/export_txt.py` (pdfplumber page text, pages separated by form feeds) |
| Markdown | `data/docling/AAPL_10K_20250927.md` | Docling, Part 4 |
| JSONL | `data/export/AAPL_10K_20250927.docling.jsonl` | `src/export.py`, Part 5 schema, Docling path |
| JSON (lossless) | `data/docling/AAPL_10K_20250927.json` | Docling, Part 4 |

The traditional-path JSONL and Markdown (`data/export/{stem}.jsonl`, `.md`) could not be produced yet: they need `data/layout` from Part 3 (#100, not merged), and `export.py` skips that path cleanly without it.

## Size, tokens and provenance

Approximate tokens = characters / 4, as the brief allows.

| Format | Bytes | Characters | ≈ Tokens | Page provenance (measured in the file) |
|---|---:|---:|---:|---|
| TXT | 207,983 | 206,238 | **51,559** | 61 pages separated by form feeds; no positions |
| Markdown | 277,739 | 277,650 | 69,412 | 2 HTML comments; effectively no page markers |
| JSONL | 449,948 | 449,859 | 112,464 | **604 / 604 records with page + bbox** |
| JSON | 3,658,987 | 3,658,987 | 914,746 | 775 `page_no` entries (page + bbox per item) |

Provenance grows with size: TXT is the cheapest to send to a model and carries the least. JSONL costs about 2.2× the tokens of TXT for exact page and position on every record. The lossless JSON is about 18× TXT and does not fit a chat context.

## Three retrieval questions, same prompt per format

Prompt, sent with one file attached, in a new chat each time (Claude Opus 5.5 in claude.ai):

> Answer only from the attached file. If something is not in the file, say "not in the file".
> 1) What was Apple's net income for the fiscal year ended September 27, 2025, and on which page of the document is it reported?
> 2) What were Apple's total assets as of September 27, 2025, and on which page?
> 3) What were Apple's net sales of Products and of Services for fiscal year 2025?

Answer key: (1) $112,010M, rendered PDF p32 (printed page 29); (2) $359,241M, PDF p34 (printed 31); (3) Products $307,003M, Services $109,158M.

| Format | Q1 | Q2 | Q3 | Values correct | Where the page came from |
|---|---|---|---|---:|---|
| TXT | $112,010M, page 29 | $359,241M, page 31 | $307,003M / $109,158M | **3 / 3** | the printed footer text ("Apple Inc. \| 2025 Form 10-K \| 29") |
| Markdown | $112,010M, page 29 | $359,241M, page 31 | $307,003M / $109,158M | **3 / 3** | the 10-K's own table of contents; the model noted the file has no page markers |
| JSONL | not in the file | not in the file | not in the file | **0 / 3** | the `page` field: it located both statement headings on PDF pages 32 and 34 and reported their tables missing |
| JSON | not tested | | | — | too large for a chat context (≈915k tokens) |

What this shows:
- **TXT and Markdown answered correctly, but their page numbers are incidental.** TXT worked because the printed footer happens to be in the text; Markdown worked because the statements are listed in the 10-K's contents table. A number in a note that no contents table lists would have no page in either format.
- **JSONL failed for a known, fixable reason, and failed safely.** Every table is missing from the Docling export (`docling_blocks` skips Table blocks; raised on #105), so the numbers are not in the file; the model said so instead of guessing, and still gave exact PDF pages for the headings from the `page` field.

## Decision and why

| Role | Format | Reason (from the measurements above) |
|---|---|---|
| Source of truth | **JSONL** (Part 5 schema) | the only format with page + bbox on every record (604/604), validated by `src/schema.py`; Markdown and TXT can be regenerated from it, not the other way round |
| Feeds Case Study 2 | **JSONL** | retrieval needs a citation per chunk; each record already has page, bbox, section and block id |
| Human-readable view | Markdown | readable and 38% smaller than JSONL, but no page markers of its own |
| Baseline | TXT | smallest (51,559 tokens) and answers by text search, but carries no positions |
| Archive only | Docling JSON | lossless, but ≈915k tokens |

Condition on the decision: the JSONL that feeds Case Study 2 must include tables as structured objects (Part 5 requires this for the traditional path). Rerun the three questions on `data/export/AAPL_10K_20250927.jsonl` once Part 3 (#100) is merged.

## Limitations

- One run per format, one model; answers can vary between runs.
- The TXT run used a regular chat (account memory on); Markdown and JSONL used incognito chats. Memory holds no figures from the filing.
- The model ran code over the attached files (it searched them) rather than reading them end to end, so the test measures what a file contains and exposes, more than how well a model reads long context.
- The traditional-path JSONL and Markdown were not tested (no `data/layout` yet); the JSONL tested is the Docling export, which is text-only.
- Tokens are approximated as characters / 4, not counted with a tokenizer.
