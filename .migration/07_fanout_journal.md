# 07 — Fan-out journal

Workflow: mongo-032752-fanout (script: .migration/fanout_workflow.py)

| Date (UTC) | Event | run_id |
|---|---|---|
| 2026-09-01 | Fan-out launched | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | U0 ESCALATE (codes gate scoping, fixture_meta non-deterministic key) — halted, user approved contract amendments; resuming same run | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | Wave 0 CLOSED — U0 green (fixture + independent live recon DRIFT-EXPLAINED on fixture_meta), PR #1397 merged | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | Wave 1: U2 GREEN (fixture); U1 ESCALATE — Tier 2 aggregate semantics on 19 NULL-bearing numeric CUSTOMER_MASTER columns (Oracle COUNT DISTINCT/SUM exclude NULLs; Mongo counts the null group / $sum=0). Halted for human decision | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | U1 amendment v1.1 approved — resuming wave 1 (U1 re-run 1/3; U2 result replays) | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | Wave 1 CLOSED — U1, U2 merged on independent recon PASS; reports.py conflict resolved by orchestrator (disjoint report paths kept verbatim, U1 MONGO_SOURCE renamed MONGO_BALANCES_SOURCE) | recon/wave1-independent-20260901 |
| 2026-09-01 | U1 PR #1406 post-gate commits 02a8fd2c/e6abe951 merged after orchestrator fidelity review (app-code + tests only; no loader/data change); wave 1 recon PASS remains valid | recon/wave1-independent-20260901 |
| 2026-09-01 | U3 amendment v1.2 approved — resuming wave 2 (U3 re-run 2/3; U4/U7 results carry) | wfr-3be3387b3ba7486a90f9d1260a2427c5 |
| 2026-09-01 | Wave 2 CLOSED — U3 (v1.2 re-gate, re-run 2/3), U4, U7 merged on independent recon PASS | recon/wave2-independent-20260901 |
| 2026-09-01 | Wave 3a CLOSED — U5 merged on independent recon PASS | recon/wave3a-independent-20260901 |
| 2026-09-01 | Wave 3b CLOSED — U6 merged on independent recon PASS; fan-out complete | recon/wave3b-independent-20260901 |
