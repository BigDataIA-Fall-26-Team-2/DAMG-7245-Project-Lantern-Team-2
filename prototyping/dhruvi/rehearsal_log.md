# Section 7 reproducibility rehearsal (issue #56)

Each run executes the brief's Section 7 commands, in order, on a fresh clone with a new virtual environment: `bash prototyping/dhruvi/rehearsal.sh [WORKDIR] [LOG]`. Machine: MacBook Air (Apple silicon), macOS, Python 3.11. One recorded deviation: `python -m venv` runs as `python3.11 -m venv`, because macOS may not provide a bare `python`. The raw logs stay local, because `*.log` is gitignored; the table below records every result from them.

| Command | Run 1, main 9ece344 (after #105) | Run 2, main 8737af8 (after #103) | Run 3, main d7fcffd (after #109) |
|---|---|---|---|
| git clone | PASS | PASS | PASS |
| git checkout submission | FAIL: no tag yet | FAIL: no tag yet | FAIL: no tag yet |
| python -m venv .venv | PASS | PASS | PASS |
| pip install -r requirements.txt | PASS (27 s) | PASS (66 s) | PASS (75 s) |
| dvc pull | FAIL: not a DVC repository | FAIL: params.yaml rejected | FAIL: no remote (missing files) |
| dvc repro | FAIL: not a DVC repository | FAIL after 0 s: params.yaml rejected | **PASS (42 s): download, render, parse_pdfplumber** |
| dvc metrics show | exit 0, prints nothing | exit 0, prints nothing | exit 0, prints nothing |
| pytest -q | PASS (63 passed, 1 skipped) | PASS (91 passed, 1 skipped) | PASS (91 passed, 1 skipped) |

## What broke and how it was fixed

1. **Run 2: DVC rejected `params.yaml`.** `layout.dark_page_brightness` appeared twice (lines 54-55): #100 and #101 each added it with a different comment and the merge of main into `shravya/p4-docling` (d88f568) kept both. PyYAML keeps the last value silently, so all 91 tests passed; DVC's loader is strict and refused the file, so `dvc pull` and `dvc repro` failed before any stage ran. Fixed in #109 (one line, same value, both comments kept); run 3 confirms it.
2. **Run 3: `render` depends on a browser outside the repository.** It passed only because Playwright's Chromium was already in the shared cache `~/Library/Caches/ms-playwright`. With `PLAYWRIGHT_BROWSERS_PATH` pointed at an empty folder, as on a grader's fresh machine, `src/render.py` exits 1 at browser launch ("please run: playwright install"); after `python -m playwright install chromium` into the same folder it exits 0 and writes both PDFs. Proposed on #112: prefix the render stage command with `python -m playwright install chromium`.

## Still needed before Section 7 can pass

- A DVC remote readable by course staff, plus `dvc push`, so `dvc pull` succeeds.
- The remaining canonical stages: #112 adds tables, layout, parse_docling and export; xbrl and evaluate are still missing.
- Metrics declared in `dvc.yaml`, so `dvc metrics show` prints the evaluation results.
- The `submission` tag, created on submission day.

Not tested here: a bare Linux machine, where Chromium may also need system libraries (`playwright install --with-deps chromium`).
