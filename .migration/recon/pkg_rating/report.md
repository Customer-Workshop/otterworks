# Recon report: unit `pkg_rating`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-pkg_rating-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `full`
- Generated: 2026-09-28T00:35:18.089234+00:00

## Routine parity: 11 proven, 0 unproven, 0 failed

- Cost: `{"source_statements": 27, "source_rows_fetched": 6, "target_statements": 20, "target_rows_fetched": 6, "elapsed_s": 2.681}`
- Rerun proof: fresh `pass`, evolved `unsupported` (evolved pre_shape equals the fresh shape: nothing evolved, so the run proves only what fresh proved)

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 2 | PASS |
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 13 | PASS |
| 3 | keyed_diffs | 6 | PASS |

## Tier 0 coverage
```json
{
  "foreign_keys_out_of_scope": [
    "rating_periods: ('tenant_id',) -> ow_billing.tenants",
    "rating_periods: target FK ('tenant_id',) -> billing.tenants",
    "rating_results: ('subscription_id',) -> ow_billing.subscriptions",
    "rating_results: target FK ('subscription_id',) -> billing.subscriptions"
  ],
  "rating_periods": {
    "source": {
      "primary_key": [
        "id"
      ],
      "primary_key_informational": [],
      "unique": [
        [
          "tenant_id",
          "period_start"
        ]
      ],
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
        "period_end",
        "period_start",
        "tenant_id"
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
          "tenant_id",
          "period_start"
        ]
      ],
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
        "period_end",
        "period_start",
        "tenant_id"
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
  "rating_results": {
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
            "period_id"
          ],
          "ow_billing.rating_periods",
          [
            "id"
          ],
          "no action",
          "no action"
        ],
        [
          [
            "subscription_id"
          ],
          "ow_billing.subscriptions",
          [
            "id"
          ],
          "no action",
          "no action"
        ]
      ],
      "foreign_keys_informational": [],
      "not_null": [
        "billable_units",
        "created_at",
        "id",
        "overage_amount",
        "period_id",
        "quota_units",
        "rollover_units",
        "subscription_id",
        "used_units"
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
            "period_id"
          ],
          "billing.rating_periods",
          [
            "id"
          ],
          "no action",
          "no action"
        ],
        [
          [
            "subscription_id"
          ],
          "billing.subscriptions",
          [
            "id"
          ],
          "no action",
          "no action"
        ]
      ],
      "foreign_keys_informational": [],
      "not_null": [
        "billable_units",
        "created_at",
        "id",
        "overage_amount",
        "period_id",
        "quota_units",
        "rollover_units",
        "subscription_id",
        "used_units"
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
    "OW_BILLING.RATING_PERIODS": 3,
    "OW_BILLING.RATING_RESULTS": 3
  }
}
```

## Tier 3 coverage
```json
{
  "rating_periods": {
    "mode": "full_diff",
    "population": 3,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "rating_results": {
    "mode": "full_diff",
    "population": 3,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
