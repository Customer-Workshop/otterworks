# Recon report: unit `lakebase_scaffold`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-lakebase_scaffold-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `full`
- Generated: 2026-09-27T21:51:42.694331+00:00
- Cost: `{"source_statements": 53, "source_rows_fetched": 918, "target_statements": 38, "target_rows_fetched": 918, "elapsed_s": 11.529}`
- Rerun proof: fresh `pass`, evolved `unsupported` (evolved pre_shape equals the fresh shape: nothing evolved, so the run proves only what fresh proved)

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 4 | PASS |
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 19 | PASS |
| 3 | keyed_diffs | 918 | PASS |

## Tier 0 coverage
```json
{
  "codes": {
    "source": {
      "primary_key": [
        "code_type",
        "code_val"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "code_desc",
        "code_type",
        "code_val"
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
        "code_type",
        "code_val"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "code_desc",
        "code_type",
        "code_val"
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
  "plans": {
    "source": {
      "primary_key": [
        "id"
      ],
      "primary_key_informational": [],
      "unique": [
        [
          "code"
        ]
      ],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "active_yn",
        "code",
        "id",
        "included_units",
        "monthly_fee",
        "overage_rate",
        "tier_cd"
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
        "id"
      ],
      "primary_key_informational": [],
      "unique": [
        [
          "code"
        ]
      ],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "active_yn",
        "code",
        "id",
        "included_units",
        "monthly_fee",
        "overage_rate",
        "tier_cd"
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
  "tenants": {
    "source": {
      "primary_key": [
        "id"
      ],
      "primary_key_informational": [],
      "unique": [
        [
          "name"
        ]
      ],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "id",
        "name",
        "status_cd",
        "tax_exempt_yn"
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
        "id"
      ],
      "primary_key_informational": [],
      "unique": [
        [
          "name"
        ]
      ],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "id",
        "name",
        "status_cd",
        "tax_exempt_yn"
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
  "usage_events": {
    "source": {
      "primary_key": [
        "id"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [
        [
          [
            "tenant_id"
          ],
          "ow_billing.tenants",
          [
            "id"
          ],
          "no action",
          "no action"
        ]
      ],
      "foreign_keys_informational": [],
      "not_null": [
        "id",
        "kind_cd",
        "occurred_at",
        "tenant_id",
        "units"
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
        "id"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [
        [
          [
            "tenant_id"
          ],
          "billing.tenants",
          [
            "id"
          ],
          "no action",
          "no action"
        ]
      ],
      "foreign_keys_informational": [],
      "not_null": [
        "id",
        "kind_cd",
        "occurred_at",
        "tenant_id",
        "units"
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
    "OW_BILLING.CODES": 32,
    "OW_BILLING.PLANS": 3,
    "OW_BILLING.TENANTS": 69,
    "OW_BILLING.USAGE_EVENTS": 814
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "codes.code_type",
    "codes.code_desc",
    "plans.code",
    "plans.active_yn",
    "tenants.name",
    "tenants.tax_exempt_yn"
  ]
}
```

## Tier 3 coverage
```json
{
  "codes": {
    "mode": "full_diff",
    "population": 32,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "plans": {
    "mode": "full_diff",
    "population": 3,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "tenants": {
    "mode": "full_diff",
    "population": 69,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "usage_events": {
    "mode": "full_diff",
    "population": 814,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
