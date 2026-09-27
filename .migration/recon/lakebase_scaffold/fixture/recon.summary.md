# Recon summary: `lakebase_scaffold` - **FAIL**

- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping `map-20260927-lakebase_scaffold-v1` / tolerances `tol-20260927-v1` / seed `0` / depth `full` / params `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Generated: 2026-09-27T15:35:45.987315+00:00
- Cost: source 37 statements / 0 rows fetched; target 26 statements / 0 rows; 5.16s
- Structural checks: constraints=checked, triggers=checked, indexes=checked, sequences_identity=checked, grants=direct_only
- Rerun proof: fresh `pass`, evolved `unsupported` (evolved pre_shape equals the fresh shape: nothing evolved, so the run proves only what fresh proved)

| Tier | Checks | Result |
|---|---|---|
| 0 structural_parity | 4 | FAIL (5) |
| 1 counts_through_mapping | 4 | FAIL (2) |

Top findings (5 of 7; full list in result.json):
- T0 `codes` grant_extra: target grant dhrov.subramanian@cognition.ai (delete,insert,select,update) has no source counterpart
- T0 `plans` grant_extra: target grant dhrov.subramanian@cognition.ai (delete,insert,select,update) has no source counterpart
- T0 `tenants` grant_extra: target grant dhrov.subramanian@cognition.ai (delete,insert,select,update) has no source counterpart
- T0 `usage_events` trigger_missing: before insert row: source 1, target 0
- T0 `usage_events` grant_extra: target grant dhrov.subramanian@cognition.ai (delete,insert,select,update) has no source counterpart

Full evidence: result.json, report.md (linked from the PR, not pasted).
