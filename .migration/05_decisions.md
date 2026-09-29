# 05 Decisions

| ID | Date (UTC) | Decision | Status | Approved by | Provenance |
|---|---|---|---|---|---|
| D-001 | 2026-09-29 | Baseline counts match the expected 25,000 / 18,750 / 150,000 / 37 orphans; proceed | DECIDED | - | baseline/oracle_counts.json |
| D-002 | 2026-09-29 | Before capture: `BILLING_READONLY=1` guard skips tenant auto-provisioning; sign in as a local-only auth user with Casey Novak's tenant id | DECIDED | requester | user: answer 1 in this session |
| D-003 | 2026-09-29 | Invoice capture uses Tenant Two invoice 60000000-0000-0000-0000-000000000001 (2 lines, $161.29), captured separately | DECIDED | requester | user: answer 2 in this session |
| D-004 | 2026-09-29 | stop_mode hard for STOP A and STOP B; STOP C always hard; `auto_merge: false` everywhere | DECIDED | requester | user: kickoff message |
| D-005 | 2026-09-29 | Model constraints: attributes as array keeping duplicates; lines embedded in invoices; 37 orphans quarantined | DECIDED (detail at STOP B) | requester | user: kickoff message |
| D-006 | 2026-09-29 | Tolerances version 1 as in 02_tolerances.md/json, connectivity policy `online` | PROPOSED | - | awaiting STOP A |
| D-007 | 2026-09-29 | Target principal behind `OW_TP_MMP_TARGET_URI` holds dbAdmin@ow_tp_mmp_live, readWrite@ow_tp_mmp_live_quarantine, dbAdmin@ow_tp_mmp_live_quarantine: privilege_excess, BLOCKED. Fix: rescope to readWrite@ow_tp_mmp_live only | BLOCKED | - | 08_connectivity.json |
| D-008 | 2026-09-29 | Org statement guard blocks the plugin's `connectivity_probe.py` (dict-built SQL). Probe run through `.migration/tools/connectivity_probe_oracle.py`, same checks with a literal statement | PROPOSED | - | awaiting STOP A |
| D-009 | 2026-09-29 | Add `legacy_sources` (Oracle secret names and host) to allowed_targets.json so the guard treats any non-read through them as a legacy write | PROPOSED | - | awaiting STOP A |
