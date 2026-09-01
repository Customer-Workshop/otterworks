# 07 — Fan-out journal

Workflow: mongo-032752-fanout (script: .migration/fanout_workflow.py)

| Date (UTC) | Event | run_id |
|---|---|---|
| 2026-09-01 | Fan-out launched | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | U0 ESCALATE (codes gate scoping, fixture_meta non-deterministic key) — halted, user approved contract amendments; resuming same run | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | Wave 0 CLOSED — U0 green (fixture + independent live recon DRIFT-EXPLAINED on fixture_meta), PR #1397 merged | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | Wave 1: U2 GREEN (fixture); U1 ESCALATE — Tier 2 aggregate semantics on 19 NULL-bearing numeric CUSTOMER_MASTER columns (Oracle COUNT DISTINCT/SUM exclude NULLs; Mongo counts the null group / $sum=0). Halted for human decision | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
