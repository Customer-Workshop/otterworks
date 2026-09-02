# 08 — Parallel-run ledger

This window is opened by the parent only after approval and the staged-red drill.
The STOP E entry criterion is three consecutive green scheduled cycles.
Window state: OPEN (staged-red verified). Normal verification run `324153933407183` is pre-window.

| UTC ts | run_id | fact verdict/summary verdict | triage class or none | drift note | PR link or — |
|---|---|---|---|---|---|
| 2026-09-02T02:52:43Z | 21080242102762 | PASS/SKIPPED | STAGED RED (drill) | fact report written then forced red; summary skipped upstream; webhook → automation → session d865b74e39454c4f99991cfaefa80c68 | — |
| 2026-09-02T03:11:02Z | 353511658021615 | PASS/SKIPPED | STAGED RED (drill) | fact recon PASS (9/9 checks, idempotency rerun pass, dropped_join_rows=0) then forced red by staged_red=true on both task attempts; summary skipped upstream; r3_notify webhook 200 → automation → session 27c9958adca641c0a69b3b916b1ac759 | — |
