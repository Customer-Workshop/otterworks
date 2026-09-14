# Decision log

Provenance is `user:<message/event id>` (a human replied) or `default-accepted (soft, 60s, no reply)`.
Never `user:` without a human reply; never a default at STOP E.

| ID | Date | Decision | Options | Recommended | Outcome | Provenance | Forced by | Blast radius |
|---|---|---|---|---|---|---|---|---|
| DEC-000 | 2026-09-14 | Intake consumed as FACT from the parent's confirmed intake (`ow_billing_intake_draft.md`); `stop_mode: soft` | — | — | recorded | parent intake (confirmed with customer 2026-09-14) | front door | whole engagement |
| DEC-A | 2026-09-14 | STOP A: target profiles, track split, tolerances `tol-p1-v1`, access posture and D10-1..6 as written in `stops/STOP_A.md` | approve as-is / amend rows | approve as-is (D10-4 option (a): PAT identity accepted for this run; D10-7 option (a): convention-only write-scope enforcement; rehearsal fallback freeze-and-load until D10-1 closes; `cdc_lag_max_s: 60`; Debezium kept as the CDC path per intake) | PENDING | — | setup | all downstream |
