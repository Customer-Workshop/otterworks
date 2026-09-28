# Recon report: unit `pkg_ow_util`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-pkg_ow_util-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `full`
- Generated: 2026-09-28T00:35:09.729818+00:00

## Routine parity: 11 proven, 0 unproven, 0 failed

- Cost: `{"source_statements": 14, "source_rows_fetched": 0, "target_statements": 11, "target_rows_fetched": 0, "elapsed_s": 1.307}`
- Rerun proof: fresh `pass`, evolved `unsupported` (evolved pre_shape equals the fresh shape: nothing evolved, so the run proves only what fresh proved)

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 1 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 4 | PASS |
| 3 | keyed_diffs | 0 | PASS |

## Tier 0 coverage
```json
{
  "billing_audit_log": {
    "source": {
      "primary_key": [
        "log_id"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "log_id",
        "logged_at"
      ],
      "indexes": [],
      "check_count": 0,
      "checks": [],
      "identity_columns": [],
      "partial": [],
      "expression_unique": [],
      "expression_indexes": [],
      "triggers": {},
      "grants": {},
      "unsupported": []
    },
    "target": {
      "primary_key": [
        "log_id"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "log_id",
        "logged_at"
      ],
      "indexes": [],
      "check_count": 0,
      "checks": [],
      "identity_columns": [],
      "partial": [],
      "expression_unique": [],
      "expression_indexes": [],
      "triggers": {},
      "grants": {},
      "unsupported": []
    },
    "identity": null
  },
  "structural_checks": {
    "constraints": "checked",
    "triggers": "checked",
    "indexes": "checked",
    "sequences_identity": "checked",
    "grants": "direct_only"
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
    "OW_BILLING.BILLING_AUDIT_LOG": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "billing_audit_log.module",
    "billing_audit_log.message"
  ]
}
```

## Tier 3 coverage
```json
{
  "billing_audit_log": {
    "mode": "full_diff",
    "population": 0,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
