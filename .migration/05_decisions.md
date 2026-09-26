# 05_decisions: decision log

Provenance is `user:<message/event id>` only when a human replied; `default-accepted (soft, 60s, no reply)` when a soft window elapsed; `intake` for facts stated in the kickoff message; `orchestrator` for automatic, rule-mandated actions.

| ID | Date (UTC) | Decision | Approver / provenance | Notes |
|---|---|---|---|---|
| D-000 | 2026-09-26 | Engagement facts as in `00_context.md`: offline policy, `stop_mode` soft for A/B, STOP C hard, width 3, no reviewer, `auto_merge: false` everywhere, no PR merged on offline evidence, branch restriction to `tech-partnerships` + run branch | intake (kickoff message, session 983733d4647d4ea2b1fd4344adfa7b65) | |
| D-000a | 2026-09-26 | `allowed_targets.json` carries a `catalogs` key mirroring the single `databases` entry `ow_billing_migration`, because the co-installed dbx-migration-factory PreToolUse hook parses the same file and rejects any tool call while it lacks a non-empty `catalogs` list. No Databricks target is authorized; the mongo kit reads `databases` only | orchestrator (tool refusal recorded verbatim in `06_access_checklist.md`) | deviation from playbook 1 step 8 wording ("only the designated migration database"): same single database, extra key |
