# Recon report: unit `finance_close_gold`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-finance_close_gold-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `full`
- Generated: 2026-09-28T01:33:17.958558+00:00
- Cost: `{"source_statements": 14, "source_rows_fetched": 18750, "target_statements": 9, "target_rows_fetched": 18750, "elapsed_s": 21.612}`
- **WARNING: UNVERIFIED structural_parity: structure unavailable: finance_close_detail: finance_close_detail: information_schema.table_privileges read failed (ServerOperationError)**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 0 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 7 | PASS |
| 3 | keyed_diffs | 18750 | PASS |

## Tier 0 coverage
```json
{
  "dictionary_unavailable": [
    "finance_close_detail: finance_close_detail: information_schema.table_privileges read failed (ServerOperationError)"
  ],
  "structural_checks": {
    "constraints": "unsupported",
    "triggers": "unsupported",
    "indexes": "unsupported",
    "sequences_identity": "unsupported",
    "grants": "unsupported"
  },
  "structural_diff": {},
  "dictionary": {
    "source": "live",
    "target": "live"
  }
}
```

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.INVOICE_HEADER": 18750
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "finance_close_detail.invoice_dt"
  ]
}
```

## Tier 3 coverage
```json
{
  "finance_close_detail": {
    "mode": "full_diff",
    "population": 18750,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
