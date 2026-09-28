# Recon summary: `finance_close_gold` - **PASS**

- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping `map-20260927c-finance_close_gold-v1` / tolerances `tol-20260927c-v1` / seed `0` / depth `full` / params `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Generated: 2026-09-28T01:36:23.052940+00:00
- Cost: source 14 statements / 18750 rows fetched; target 9 statements / 18750 rows; 23.006s
- Structural checks: constraints=unsupported, triggers=unsupported, indexes=unsupported, sequences_identity=unsupported, grants=unsupported
- Rerun proof: fresh `pass`, evolved `unsupported` (no evolved record: pre-create the table in its previous committed shape (the prior proof's shape) and run again)
- **WARNING: UNVERIFIED structural_parity: structure unavailable: finance_close_detail: finance_close_detail: information_schema.table_privileges read failed (ServerOperationError)**

| Tier | Checks | Result |
|---|---|---|
| 0 structural_parity | 0 | PASS |
| 1 counts_through_mapping | 1 | PASS |
| 2 per_field_aggregates | 7 | PASS |
| 3 keyed_diffs | 18750 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
