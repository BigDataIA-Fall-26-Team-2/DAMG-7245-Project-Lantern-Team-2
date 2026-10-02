# Contributing to Project LANTERN

## Before you start any work
- `git fetch origin` and `git checkout main && git pull --ff-only` before branching — never branch off a stale `main`.
- Create a branch per task, namespaced by your name: `name/pN-shortdesc` (e.g. `sai/p0-download`, `priya/p5-schema`) when the work maps to a Case Study Part. If it doesn't map to a Part (infra, a bugfix, docs), drop the part number: `name/shortdesc` (e.g. `sai/fix-xbrl-scale-bug`).

## Workflow
1. Branch from up-to-date `main`.
2. Make one focused change — one Part, or one bug, per branch/PR. Don't bundle unrelated Parts.
3. Before opening a PR: `dvc repro` locally for any stage you touched, `pytest -q`, and re-check `params.yaml` has no hardcoded values you introduced.
4. Open a PR against `main` using the template — fill every section, including the AI Engineering Log if you used AI assistance.
5. At least one teammate (not the author) must approve before merge. CODEOWNERS auto-requests a reviewer; re-request if they haven't responded in a day.
6. Squash-merge, delete the branch.

## Keeping in sync
- `git pull --rebase` on your branch before pushing if `main` has moved.
- `dvc pull` after every `git pull` that touches `data/` pointers — a stale DVC cache produces misleading local results.
- If you add a new tool/library: pin it in `requirements.txt` (or `requirements-ci.txt` if CI-only), and add one row to the "Tools in use" table in `README.md` so the whole team knows it exists before they hit it as a surprise import error.

## Code review focus
Reviewers check, in this order:
1. Does it meet the Part's acceptance criteria from Case Study 1?
2. Is every number or claim in a report backed by a file the grader can see (CSV row, JSON field, cited price page)?
3. No hardcoded paths, thresholds, or secrets?
4. Are there tests/evidence for the specific failure mode this Part cares about (OCR trigger, table mismatch, XBRL mismatch, etc.)?

## Reporting AI usage
Every PR that used AI assistance (Claude, ChatGPT, Copilot, etc.) must fill the AI Engineering Log section of the PR template. This rolls up directly into the semester-end AI Engineering Log required by the syllabus — log it per PR now, don't reconstruct it from memory later.

## Who owns what
See `WORKPLAN.md` for the Part-by-Part ownership matrix and milestones.
