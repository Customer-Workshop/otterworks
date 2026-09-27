# Recon report: unit `pkg_ow_util`

- **Verdict: FAIL**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-pkg_ow_util-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `full`
- Generated: 2026-09-27T22:57:14.739330+00:00

## Routine parity: routine_parity_missing (the unit has writing routines and no parity list; run `dbx-recon routine-parity` and pass `--routine-parity`)

- `ow_billing.pkg_ow_util.log_msg` no row
- `ow_billing.job_purge_audit_log` no row
- Cost: `{"source_statements": 14, "source_rows_fetched": 0, "target_statements": 11, "target_rows_fetched": 0, "elapsed_s": 1.21}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 1 | FAIL (1 findings) |
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
      "identity_columns": [
        "log_id"
      ],
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
  "structural_diff": {
    "billing_audit_log": {
      "sequences_identity": [
        "target log_id is identity but source log_id is not: target-generated keys diverge from the source's"
      ]
    }
  },
  "dictionary": {
    "source": "live",
    "target": "live"
  }
}
```

## Tier 0 findings (1)
- `billing_audit_log` identity_extra: target log_id is identity but source log_id is not: target-generated keys diverge from the source's

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
