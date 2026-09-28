# Recon summary: `pkg_plans` - **FAIL**

- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping `map-20260927c-pkg_plans-v1` / tolerances `tol-20260927c-v1` / seed `0` / depth `full` / params `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Generated: 2026-09-28T00:24:47.471919+00:00
- Cost: source 27 statements / 69 rows fetched; target 20 statements / 69 rows; 2.033s

## Routine parity: 11 proven, 0 unproven, 0 failed

- Structural checks: constraints=checked, triggers=checked, indexes=checked, sequences_identity=checked, grants=direct_only

| Tier | Checks | Result |
|---|---|---|
| 0 structural_parity | 2 | FAIL (4) |
| 1 counts_through_mapping | 2 | PASS |
| 2 per_field_aggregates | 17 | PASS |
| 3 keyed_diffs | 69 | PASS |

Top findings (4 of 4; full list in result.json):
- T0 `subscriptions` trigger_extra: after delete row: target 1, source 0: writes the legacy app makes today behave differently
- T0 `subscriptions` trigger_extra: after update row: target 1, source 0: writes the legacy app makes today behave differently
- T0 `subscriptions` trigger_extra: before update row: target 1, source 0: writes the legacy app makes today behave differently
- T0 `subscriptions_hist` identity_extra: target hist_id is identity but source hist_id is not: target-generated keys diverge from the source's

Full evidence: result.json, report.md (linked from the PR, not pasted).
