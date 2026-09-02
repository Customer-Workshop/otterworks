# 08 — Parallel-run ledger

This window is opened by the parent only after approval and the staged-red drill.
The STOP E entry criterion is three consecutive green scheduled cycles.

| UTC ts | run_id | fact verdict/summary verdict | triage class or none | drift note | PR link or — |
|---|---|---|---|---|---|
| 2026-09-02T02:54:10Z | 21080242102762 | STAGED RED (drill) — fact PASS (9/9 checks, idempotency pass) / summary NOT RUN (UPSTREAM_FAILED, no report) | none (drill) | none — r1 failed only on the `STAGED RED RUN` guard after a PASS report was written; r2 skipped by design | — |
