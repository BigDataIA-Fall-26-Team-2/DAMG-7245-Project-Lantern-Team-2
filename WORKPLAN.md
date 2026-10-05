# LANTERN Work Plan

Case Study 1 is graded as 11 Parts + docs (100 pts + 5 bonus). Team deadline: **Friday, Oct 9, 2026**. This tracks ownership and the sprint plan so work doesn't collide — see `CONTRIBUTING.md` for how reviews work once a Part is in flight.

| Part | Theme | Pts | Tutorial Lab | Owner | Status |
|---|---|---|---|---|---|
| P0 | Repo + dataset bootstrap | 5 | Lab 0 | Lokesh | Not started |
| P1 | Text extraction + OCR fallback | 7 | Lab 1 | Teammate 2 | Not started |
| P2 | Table extraction, hybrid extractor | 10 | Lab 2 | Teammate 3 | Not started |
| P3 | Layout detection + routing | 6 | Lab 3 | Teammate 3 | Not started |
| P4 | Docling path + comparison | 8 | Lab 4 | Teammate 4 | Not started |
| P5 | Metadata + provenance schema | 8 | Lab 5 | Teammate 4 | Not started |
| P6 | Storage format decision | 4 | Lab 6 | Teammate 2 | Not started |
| P7 | Build vs buy (managed doc AI — AWS Textract) | 7 | Lab 7 | Lokesh | Not started |
| P8 | DVC pipeline + CI (S3 remote) | 10 | Lab 8 | Lokesh | Not started |
| P9 | Evaluation + regression tests | 10 | Lab 9 | Teammate 2 | Not started |
| P10 | Cost/throughput benchmarking | 5 | Lab 10 | Teammate 4 | Not started |
| P11 | XBRL extraction + validation | 10 | Lab 11 | Teammate 3 | Not started |
| Docs | README, Codelab, demo video | 10 | — | all | Not started |

Points per person: Lokesh 22, Teammate 2 21, Teammate 3 26, Teammate 4 21 — close enough to equal for the attestation; adjust if someone's actual time investment (e.g. infra work below) runs heavier than their point share suggests. Swap in real names once the team confirms on today's call.

## Infra tasks (team's own choice, not part of the 11 graded Parts)
- **S3 bucket as the DVC remote** — folded into Lokesh's P8, not a separate task. This *is* graded (Part 8 requires a remote course staff can read).
- **AWS Textract** — folded into Lokesh's P7, not a separate task. This *is* graded (one of three allowed managed services for Part 7).
- **Dockerfile** — new, owned by Lokesh, Day 1-2. Installs system packages (Tesseract, Poppler, etc.) + `requirements.txt` so all four people get the same environment instead of fighting installs individually. This is **not** part of the official reproducibility contract (Section 7 runs on a clean Linux box via plain `venv` + `pip install`, not Docker) — keep it to one Dockerfile for dev consistency, not a multi-service deployment setup.
- **A deployed, running app on AWS** — explicitly **out of scope for Case Study 1** (it's Case Study 5 territory per the syllabus). Treat as a post-deadline stretch only; don't let it take time from the graded Parts this week.

## This week's sprint plan (Fri Oct 2 kickoff → deadline Fri Oct 9)
Nobody waits on P0 to start — three of four tracks have an independent entry point on Day 1:

- **Day 1-2:** Lokesh ships P0 (download + render) and merges it ASAP — it unblocks P1/P2/P3/P4/P7. In parallel: Lokesh also stands up the S3 DVC remote, a CI skeleton, and the Dockerfile. Teammate 2 starts P9 ground-truth transcription (needs only sample EDGAR pages, not the pipeline). Teammate 3 starts P11/XBRL (needs only the raw unpacked filing, which lands before rendering does). Teammate 4 prototypes P4/Docling and drafts the P5 schema against a manually-downloaded sample filing.
- **Day 2-4:** With P0 merged, P1/P2/P3/P4/P7 all branch off real rendered PDFs in parallel. P5 (schema) gets finalized once P1-P4 emit real output, not before.
- **Day 4-5:** Integration — every stage gets real `deps`/`params`/`outs` registered in `dvc.yaml`. P9 eval and P10 benchmarks run against the real pipeline.
- **Day 6:** Harden — run the actual reproducibility contract on a clean clone (`dvc pull && dvc repro && pytest -q`), fix whatever breaks.
- **Day 7 (Thu):** Docs — README, Codelab, demo video. Tag and `dvc push` a day before the deadline, not on it.

Daily 30-min standup: the one question that matters is "what's blocking you, and whose PR do you need reviewed to unblock?" — everything else can move async.

## Dependency order (why this sequencing)
Download → Render → [Text/OCR, Tables] → Layout → Docling → Metadata schema → Formats → Build-vs-buy → DVC pipeline → Evaluation/Benchmarks ← XBRL.

- Metadata (P5) can't be designed before P1-P4 exist — the schema is built from what they actually emit.
- Evaluation (P9) and benchmarking (P10) need the DVC pipeline (P8) running end-to-end.
- XBRL (P11) feeds the ground truth that P9's regression tests check against.

## Attestation reminder
Final submission needs a contribution-percentage attestation per the syllabus's AI-use and academic-integrity policy. Keep the Owner column above roughly honest as you go instead of reconstructing it at the end.
