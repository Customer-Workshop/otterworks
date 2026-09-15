# 05 Decisions

The record of every stop and every amendment. A decision that is not a row here does not
exist, whatever the chat says. Provenance is `user:<message id>` only when a human replied;
silence in soft mode is `default-accepted (soft, 60s, no reply)`.

| # | Date | Decision | Provenance | Notes |
|---|---|---|---|---|
| 1 | 2026-09-15 | Engagement opened. `stop_mode: soft`, STOP B hard, STOP C always hard. PRD v1.0 is the binding target model. | user:engagement request | `00_context.md` |
| 2 | 2026-09-15 | **STOP A accepted.** Tolerances v1 as written in `02_tolerances.json` (exact numeric/date, money aggregates 0.01, row threshold 100000, source concurrency 2, rerun cap 3, `null_missing_equiv`, empty string → `null`). Anomaly budget frozen at 37/50/31, compared as a set; any deviation is a finding, never a tolerance change. Recon LIVE, parent-only; children `fixture` mode. Fan-out width 4. Grading-only amendments pre-authorised. | default-accepted (soft, 60s, no reply) | STOP A posted 2026-09-15; no reply in window |
| 3 | 2026-09-15 | **Read-only posture accepted as a discipline, not a grant.** No read-only Oracle account exists (`OW_BILLING` schema owner only, write-capable); creating one would write to the source. Mitigations in `06_access_checklist.md` A2. Carried as D4-1. | default-accepted (soft, 60s, no reply) | requester asked for this on record |
| 4 | 2026-09-15 | **Working branch `tp-run/mongodb-20260915T045208Z`**, cut fresh from `tech-partnerships`. The branch named at intake did not exist; every older `tp-run/mongodb-*` already carries a finished run. | default-accepted (soft, 60s, no reply) | reversible: reply `use <branch>` and the workspace moves |
