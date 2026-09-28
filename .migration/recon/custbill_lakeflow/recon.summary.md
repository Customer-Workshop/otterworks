# Recon summary: `custbill_lakeflow` - **PASS**

- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping `map-20260927c-custbill_lakeflow-v1` / tolerances `tol-20260927c-v1` / seed `0` / depth `sampled` / params `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Generated: 2026-09-28T00:22:34.270564+00:00
- Cost: source 491 statements / 304344 rows fetched; target 338 statements / 152108 rows; 495.525s

## Routine parity: routine_parity_missing (no dependency analysis; commit .migration/units/custbill_lakeflow/dependencies.json, an empty `routines` list for a unit that writes nothing, or pass `--routine-dependencies`)
- Structural checks: constraints=unsupported, triggers=unsupported, indexes=unsupported, sequences_identity=unsupported, grants=unsupported
- **WARNING: UNVERIFIED structural_parity: structure unavailable: invoice_header: invoice_header: information_schema.table_privileges read failed (ServerOperationError)**
- **WARNING: UNVERIFIED structural_parity: structure unavailable: invoice_line: invoice_line: information_schema.table_privileges read failed (ServerOperationError)**
- **WARNING: UNVERIFIED structural_parity: structure unavailable: customer_master: customer_master: information_schema.table_privileges read failed (ServerOperationError)**
- **WARNING: UNVERIFIED structural_parity: structure unavailable: entity_attr_value: entity_attr_value: information_schema.table_privileges read failed (ServerOperationError)**

| Tier | Checks | Result |
|---|---|---|
| 0 structural_parity | 0 | PASS |
| 1 counts_through_mapping | 4 | PASS |
| 2 per_field_aggregates | 191 | PASS |
| 3 keyed_diffs | 152108 | PASS |

Full evidence: result.json, report.md (linked from the PR, not pasted).
