# Ground truth transcription conventions

Part 9. Written before any transcription began, and before looking at any
parser output. Eighteen distinct pages were transcribed across the 20 sample
slots: the multi-column fixture fills that slot for both filings and was typed
once.

Rules added after transcription began are marked **(added during
transcription)** and the reason is given, so that nothing reads as having been
decided in advance when it was not.

## Source

Transcribed by eye from 150 DPI PNG renderings of the pages in
data/ground_truth/pages/, generated with pdftoppm from the rendered PDFs.
No parser output, text layer, copy-paste or clipboard extraction was used at
any point. This matters: the rendered PDF's text layer contains artifacts a
human reader never sees, for example the token "g6614" where the Apple logo
sits on 10-K page 1. Copy-pasting would have hidden that from the metrics.

## What is transcribed

- Cover, statement and notes pages: the full page body.
- Prose pages: the full page body.
- Running headers and footers are skipped: the "Apple Inc. | 2025 Form 10-K"
  line and the standalone page number. These are page furniture, not content,
  and including them would reward or punish a parser for a decision that has
  nothing to do with reading the filing.
- Reading order follows the visual order a human reads: top to bottom, and for
  a table, row by row left to right.

## Characters and symbols

- Negative numbers printed in parentheses are transcribed in parentheses,
  for example (1,234). Parentheses are never converted to a minus sign.
  Sign is financial meaning, not formatting.
- Thousands separators are kept as printed: 112,010 not 112010.
- Currency symbols are kept where printed, including a $ that appears only
  on the first row of a column.
- Percent signs, decimal points and par values are kept as printed.
- Checkboxes on the cover page are transcribed as `[X]` for a ticked box and
  `[ ]` for an unticked box. The tick carries legal meaning on a 10-K cover,
  so the distinction is preserved, but the printed glyphs (U+2610, U+2611,
  U+2612) are folded to these ASCII forms because they are not reliably
  encodable on every platform: an unencoded write of U+2612 is what crashed
  the Part 1 stage on Windows. The same folding is applied to the parser
  output at scoring time in src/evaluate.py, so neither side is penalised.
- Superscript registered-trademark and trademark symbols, ® and ™, are
  omitted. They are typographic marks attached to a brand name, not words a
  reader speaks, and they appear dozens of times across the prose pages.
  Omitting them consistently on the reference side is fair as long as the
  same characters are stripped from the parser output at scoring time, which
  src/evaluate.py does.
- Typographic quotation marks and apostrophes are transcribed as their
  straight ASCII equivalents, so "Company's" not "Company’s". The same
  substitution is applied to the parser output at scoring time.
- An em dash used as a placeholder for "no value", for example in the trading
  symbol column of the cover page or an empty year column in a statement, is
  transcribed as a plain ASCII hyphen. The same substitution is applied to the
  parser output at scoring time, so neither side is penalised for a
  typographic choice. An em dash used as punctuation inside a sentence is
  transcribed the same way.
- **(added during transcription)** Text that is part of a logo or image and
  cannot be read as words is recorded as `[unreadable]`. Used once, for the
  logo on the multi-column fixture page. The alternative was guessing at
  letterforms, which would have put an invented string into the reference.

## Footnote markers

- Superscript footnote reference markers attached to a label, for example a
  raised (1), are transcribed inline in parentheses immediately after the
  label text with no space, for example "Total net sales(1)".
- The footnote body text at the bottom of the page is transcribed as a
  separate line, prefixed by its marker in parentheses.

## Line breaks and hyphenation

- A single newline is used where the page starts a new line inside the same
  paragraph; this is then collapsed by the whitespace normalization at
  scoring time, so it carries no scoring weight.
- A blank line separates paragraphs.
- A word broken across two lines by a hyphen is joined into one word and the
  hyphen is dropped, for example "manufac-" plus "turing" becomes
  "manufacturing". A hyphen that is part of the word itself, for example
  "third-party", is kept.
- Table rows are one line each, with cells separated by a single tab.

## Normalization applied at scoring time, not at transcription time

Transcription records what is printed. Normalization happens in
src/evaluate.py and is applied identically to both the reference and the
hypothesis: lower-casing, collapsing of multiple spaces, and stripping of
leading and trailing whitespace. Punctuation is NOT removed, because
removing it turns (1,234) into 1234 and hides a sign error.

## Tables

- Stored as {doc}_p{n}_t{k}.gt.csv with four columns: row_label, col_label,
  raw, value. One line per cell, rather than the printed grid, because the
  required metric is cell precision and recall: in a grid, a cell's identity
  comes from its position, and a single dropped row shifts every position
  below it so that almost every cell scores wrong. With the row and column
  label written onto each cell, a dropped row is one missing line.
- col_label is transcribed literally as printed, including capitalisation and
  punctuation, for example "September 27, 2025" with the comma. Two
  independent transcriptions can then be diffed without false mismatches
  caused by formatting choices.
- row_label is transcribed as printed, with one exception.
  **(added during transcription)** Where a row label appears more than once on
  the page under different section headings, the section heading is prefixed
  with a colon and a space: "Net sales: Products" as distinct from
  "Cost of sales: Products". Four labels on 10-K p32 (Products, Services,
  Basic, Diluted) and two on 10-Q p6 (Marketable securities, Term debt) repeat
  this way. Without the prefix, a row label plus a column label identifies two
  different cells and those cells would be scored against the wrong figures.
  Rows that sit outside any subsection, such as "Total assets", are not
  prefixed.
- raw is the cell exactly as printed, for example "(1,234)" or "112,010".
- value is the number in full units after applying the scale.
  **(added during transcription)** The scale is per row, not per page. 10-K p32
  mixes three: dollar rows are millions (112,010 becomes
  112010000000), share-count rows are thousands (14,948,500 becomes
  14948500000) and per-share rows are unit scale (7.49 stays 7.49). 10-Q p6 is
  uniform millions. A single page-level scale would have been wrong on p32.
- An empty cell is recorded as an empty raw and an empty value, not omitted,
  so that a structural shift is detectable. Bare section-heading rows are
  recorded the same way.
- The files are written by scripts/write_gt_tables.py, which reshapes the
  keyed grid into one line per cell and applies the per-row scale. Do not open
  the CSVs in a spreadsheet: Excel reinterprets the value column as scientific
  notation and saves it back rounded to three significant figures, which
  silently turned 307003000000 into 307000000000 and produced a table cell F1
  of exactly 0.0 with no error message. tests/test_quality.py now guards
  against this.

## Verification independent of the metric

Both hand-keyed tables were checked arithmetically before being scored against
anything: all three columns of 10-K p32 reconcile from net sales through to
net income and both EPS figures, and 10-Q p6 balances in both periods with
every subtotal adding up. A single mis-keyed digit would have broken one of
those sums. This is deliberately independent of the parser comparison, so a
perfect cell F1 is not the only evidence that the reference is right.

## Known limitations

- One company, two filings. No cross-company generalisation is claimed.
- Multi-column and scanned strata come from the repository fixtures
  (tests/fixtures/multicolumn.pdf, tests/fixtures/scanned.pdf) because
  neither filing contains a multi-column prose page or a scanned page.
- Transcription is by one person except for the two statement tables keyed
  independently by a second person and reconciled, per the Lab 9 protocol
  (issue #27).
- Four files retain the page footer line against the rule above: 10-K p1, p5
  and p6, and multicol_p1. Found while scoring rather than while transcribing.
  The effect is a few extra reference words on those pages, which raises their
  WER slightly; it is recorded here rather than silently corrected after the
  numbers were seen.
- 10-Q page 7 is excluded from the sample. It is blank and wrongly triggers
  OCR, so word error rate on it would be meaningless. The page is still a real
  defect and feeds the OCR-share drift signal in reports/metrics.json.