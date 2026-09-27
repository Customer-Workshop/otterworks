# Recon summary: `lakebase_scaffold` - **PASS**

- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping `map-20260927c-lakebase_scaffold-v1` / tolerances `tol-20260927c-v1` / seed `0` / depth `full` / params `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Generated: 2026-09-27T22:36:33.074486+00:00
- Cost: source 53 statements / 918 rows fetched; target 38 statements / 918 rows; 5.159s
- Structural checks: constraints=checked, triggers=checked, indexes=checked, sequences_identity=checked, grants=direct_only
- Rerun proof: fresh `pass`, evolved `unsupported` (evolved pre_shape equals the fresh shape: nothing evolved, so the run proves only what fresh proved)

| Tier | Checks | Result |
|---|---|---|
| 0 structural_parity | 4 | PASS |
| 1 counts_through_mapping | 4 | PASS |
| 2 per_field_aggregates | 19 | PASS |
| 3 keyed_diffs | 918 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
