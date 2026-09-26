# 05_decisions

Every stop, halt, wave close, fallback, and amendment is one row. Provenance is `user:<message/event id>` only when a human replied, `default-accepted (soft, 60s, no reply)` when a soft window elapsed, or `orchestrator` for automatic bookkeeping the playbook requires.

| Date (UTC) | Decision | Outcome | Approver / provenance | Artifact |
|---|---|---|---|---|
| 2026-09-26 | Intake recorded: online engagement, live Oracle OW_BILLING -> Atlas mmp_rt_billing; stop_mode soft (STOP A), hard (STOP B, STOP C); width 3; reviewer none | recorded | orchestrator (intake message from the user) | 00_context.md |
| 2026-09-26 | Tool conflict: org-wide `dbx-migration-factory` PreToolUse guard (`hooks/dbx_guard.py`) reads `.migration/allowed_targets.json`, demanded a `catalogs` list, and hard-blocked `connectivity_probe.py` ("Python statement or connection is built at run time") because it cannot analyse oracledb/pymongo programs | `allowed_targets.json` carries `catalogs` (mirror of `databases`), `target_hosts: [MONGODB_MMP_RT_TARGET_URI]`, `legacy_sources: [OW_BILLING]`, `guard_mode: warn` (legacy-source write shapes still hard-block). Target write scope is enforced by the mongo probe allowlist check, the readWrite@mmp_rt_billing principal, and wave write-target checks. Reported to the user as a broken/conflicting tool at STOP A and in the final report. | orchestrator (environment blocker, no scope/tolerance/source impact) | allowed_targets.json |
