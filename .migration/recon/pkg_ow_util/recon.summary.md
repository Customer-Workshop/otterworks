# Recon summary: `pkg_ow_util` - **FAIL**

- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping `map-20260927c-pkg_ow_util-v1` / tolerances `tol-20260927c-v1` / seed `0` / depth `full` / params `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Generated: 2026-09-27T22:57:14.739330+00:00
- Cost: source 14 statements / 0 rows fetched; target 11 statements / 0 rows; 1.21s

## Routine parity: routine_parity_missing (the unit has writing routines and no parity list; run `dbx-recon routine-parity` and pass `--routine-parity`)

- `ow_billing.pkg_ow_util.log_msg` no row
- `ow_billing.job_purge_audit_log` no row
- Structural checks: constraints=checked, triggers=checked, indexes=checked, sequences_identity=checked, grants=direct_only

| Tier | Checks | Result |
|---|---|---|
| 0 structural_parity | 1 | FAIL (1) |
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 4 | PASS |
| 3 keyed_diffs | 0 | PASS |

Top findings (1 of 1; full list in result.json):
- T0 `billing_audit_log` identity_extra: target log_id is identity but source log_id is not: target-generated keys diverge from the source's

Full evidence: result.json, report.md (linked from the PR, not pasted).
