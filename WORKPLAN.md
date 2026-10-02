# LANTERN Work Plan

Case Study 1 is graded as 11 Parts + docs (100 pts + 5 bonus). This tracks ownership and milestones so work doesn't collide. Fill in owners once the team decides the split — see `CONTRIBUTING.md` for how reviews work once a Part is in flight.

| Part | Theme | Pts | Tutorial Lab | Owner | Status |
|---|---|---|---|---|---|
| P0 | Repo + dataset bootstrap | 5 | Lab 0 | _TBD_ | Not started |
| P1 | Text extraction + OCR fallback | 7 | Lab 1 | _TBD_ | Not started |
| P2 | Table extraction, hybrid extractor | 10 | Lab 2 | _TBD_ | Not started |
| P3 | Layout detection + routing | 6 | Lab 3 | _TBD_ | Not started |
| P4 | Docling path + comparison | 8 | Lab 4 | _TBD_ | Not started |
| P5 | Metadata + provenance schema | 8 | Lab 5 | _TBD_ | Not started |
| P6 | Storage format decision | 4 | Lab 6 | _TBD_ | Not started |
| P7 | Build vs buy (managed doc AI) | 7 | Lab 7 | _TBD_ | Not started |
| P8 | DVC pipeline + CI | 10 | Lab 8 | _TBD_ | Not started |
| P9 | Evaluation + regression tests | 10 | Lab 9 | _TBD_ | Not started |
| P10 | Cost/throughput benchmarking | 5 | Lab 10 | _TBD_ | Not started |
| P11 | XBRL extraction + validation | 10 | Lab 11 | _TBD_ | Not started |
| Docs | README, Codelab, demo video | 10 | — | all | Not started |

## Milestones (Case Study 1, Section 10)
- **End of Week 1:** Parts 0-3 — repo, download, render, fixtures, text+OCR, table bake-off, layout audit. Start ground-truth collection now; Part 9 needs it later and it's slow to build under deadline pressure.
- **End of Week 2:** Parts 4-8 — Docling path, metadata schema, one managed service, full DVC pipeline + CI.
- **Deadline:** Parts 9-11 + docs — metrics, regression tests, benchmarks, XBRL validation, README/Codelab/video. These carry 25 of the 100 points; don't leave them to the last two days.

## Dependency order (why this sequencing)
Download → Render → [Text/OCR, Tables] → Layout → Docling → Metadata schema → Formats → Build-vs-buy → DVC pipeline → Evaluation/Benchmarks ← XBRL.

- Metadata (P5) can't be designed before P1-P4 exist — the schema is built from what they actually emit.
- Evaluation (P9) and benchmarking (P10) need the DVC pipeline (P8) running end-to-end.
- XBRL (P11) feeds the ground truth that P9's regression tests check against.

## Attestation reminder
Final submission needs a contribution-percentage attestation per the syllabus's AI-use and academic-integrity policy. Keep the Owner column above roughly honest as you go instead of reconstructing it at the end.
