# Project LANTERN — AI assistant rules

This file is the shared contract for whichever AI coding assistant you use — Claude, Codex, Copilot, or anything else. Open it at the start of every session and follow it regardless of tool. It encodes the Case Study 1 grading contract — deviating from it costs points, not just style.

No `CLAUDE.md`, `AGENTS.md`, or other tool-specific stub files — this is the only copy. If your assistant doesn't auto-load `SKILLS.md`, paste it in yourself at the start of the session.

## Non-negotiable structure
- Repo layout, DVC stage names (`download, render, parse_pdfplumber, tables, layout, parse_docling, export, xbrl, evaluate`), and `data/` subfolder names are fixed by the assignment (Case Study 1, Appendix A). Do not rename or restructure them, even if a different name reads better.
- One script per DVC stage; each stage reads one upstream folder and writes one downstream folder (see Case Study 1, Section 5 diagram).
- Every tunable (thresholds, DPI, model names, tickers, dates, user-agent) goes in `params.yaml`. Never hardcode a value a grader would need to change to reproduce on a different filing.

## Code hygiene
- No redundant functions. Before writing a helper, search the repo for an existing one that already does it (bbox conversion, number normalization, manifest lookups, etc.) and reuse or extend it instead of copy-pasting.
- Keep the file structure flat and close to Appendix A's layout. A new script almost always belongs in an existing folder (`src/`, `tests/`, `reports/`) — don't create a new subfolder just because a new Part or tool showed up. Only split out a subfolder once a folder is genuinely crowded with unrelated files, not preemptively.
- No huge comment blocks on new functions, classes, or files. One or two lines max, only when the *why* isn't obvious from the code itself (a workaround, a non-obvious constraint) — never a line-by-line narration of *what* the code does.
- No unnecessary fields in the metadata/JSONL schema (Appendix B) or any other data structure. Match what the schema actually requires; don't add speculative fields "just in case" — extend the schema in a PR when a real need shows up.
- No commented-out dead code. Delete it; git history keeps it if anyone needs it back.
- Fail loudly, no silent fallbacks. A pipeline stage must error or log clearly on failure, never swallow an exception and produce a plausible-looking but wrong result — a silent failure here is exactly what the grading rubric penalizes.
- No hidden randomness. Any stochastic step (OCR thresholds, sampling, splits) needs a seed recorded in `params.yaml`; "it worked on my machine" isn't reproducible.

## Secrets and network
- Never commit API keys, AWS/GCP/Azure credentials, or tokens.
- Local secrets go in `.env` (gitignored). Since the pipeline also runs in Docker, container-specific overrides go in a separate `.env.docker` (also gitignored) — never bake either into an image.
- For CI and any shared/automated runs, use GitHub Actions secrets. Never commit a `.env` file of any name, anywhere.
- Anything exercised by CI (`.github/workflows/smoke.yml`) must run against `tests/fixtures/` only — no EDGAR, no cloud document-AI calls, no DVC remote access from CI.

## When you add or change a tool
- Pin the version in `requirements.txt` (`requirements-ci.txt` if CI-only, `requirements-colab.txt` if it's a frozen/Colab-only stage).
- Add one row to the "Tools in use" table in `README.md`.
- If it changes a DVC stage's behavior, update that stage's `deps`/`params`/`outs` in `dvc.yaml` in the same PR.

## Evidence over claims
Every number in a `reports/*.md` file must trace to a CSV row, a JSON field, or a cited price page — never an unmeasured impression ("looks accurate"). This is a direct grading criterion (30% of each Part's score).

## Test scope
- Keep recurring CI checks limited to explicit case-study requirements unless the user requests more. Do not turn one-off assistant verification into recurring workflow steps; cite the assignment requirement for any added check.
- Add persistent tests only when required by the assignment or explicitly requested by the user. Identify the requirement each added test satisfies; do not add tests merely because an assistant performed a check during implementation.
- Run one-off verification commands or temporary scripts as needed, but keep them outside the tracked repository. Record actual results and limitations in the AI Engineering Log when appropriate.
- Run existing relevant tests and retain assignment-required tests, including P9 quality regressions and CI checks. Do not expand the test suite with redundant checks or tests that only mirror the implementation.

## AI Engineering Log
When you do substantive work on a PR, draft the AI Engineering Log section of the PR template for the author to review before they submit: tool/model used, what you contributed, how it was verified, at least one failure/limitation you found, and a one-line confidence statement. Only report verification steps that were actually run.

## Working style
- For Lokesh's work, always use the `lokesh/` branch prefix, never `codex/`. Follow `CONTRIBUTING.md`: `lokesh/pN-shortdesc` for Part work and `lokesh/shortdesc` for other tasks.
- Keep changes local for the user's inspection and testing. Do not push commits or create a pull request without the user's explicit approval for that action; prior approval for another change does not authorize future pushes or PRs.
- Small, reviewable PRs: one Part or one bug per branch. Don't bundle multiple Case Study Parts in one PR.
- Commit in small, logical increments as you go — not one giant commit per checkpoint/Part. Each commit should be independently understandable (e.g. "add OCR trigger thresholds", "wire OCR log into params.yaml") so review and `git bisect` stay useful.
- See `CONTRIBUTING.md` for the human workflow and `WORKPLAN.md` for who owns which Part.

## Review discipline
Scrutinize the actual proposed change, don't rubber-stamp it — at both points below:
- **At plan time**, before writing code: does this plan really satisfy the Part's acceptance criteria, is it the simplest approach, and does it duplicate something that already exists?
- **At code-review time**, before approving a PR: re-derive whether the diff does what the PR description claims, check it against `CONTRIBUTING.md`'s review-focus order, and push back if a claim isn't backed by evidence in the PR.
