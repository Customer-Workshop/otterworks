# Recon report: unit `pkg_plans`

- **Verdict: FAIL**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-pkg_plans-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `full`
- Generated: 2026-09-28T00:24:47.471919+00:00

## Routine parity: 11 proven, 0 unproven, 0 failed

- Cost: `{"source_statements": 27, "source_rows_fetched": 69, "target_statements": 20, "target_rows_fetched": 69, "elapsed_s": 2.033}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 2 | FAIL (4 findings) |
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 17 | PASS |
| 3 | keyed_diffs | 69 | PASS |

## Tier 0 coverage
```json
{
  "foreign_keys_out_of_scope": [
    "subscriptions: ('plan_id',) -> ow_billing.plans",
    "subscriptions: ('tenant_id',) -> ow_billing.tenants",
    "subscriptions: target FK ('plan_id',) -> billing.plans",
    "subscriptions: target FK ('tenant_id',) -> billing.tenants"
  ],
  "subscriptions": {
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
            "plan_id"
          ],
          "ow_billing.plans",
          [
            "id"
          ],
          "no action",
          "no action"
        ],
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
        "plan_id",
        "starts_on",
        "status_cd",
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
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [
        [
          [
            "plan_id"
          ],
          "billing.plans",
          [
            "id"
          ],
          "no action",
          "no action"
        ],
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
        "plan_id",
        "starts_on",
        "status_cd",
        "tenant_id"
      ],
      "indexes": [],
      "check_count": 0,
      "checks": [],
      "identity_columns": [],
      "partial": [],
      "expression_unique": [],
      "expression_indexes": [],
      "triggers": {
        "trg_sub_no_uncancel": [
          "before",
          [
            "update"
          ],
          "row"
        ],
        "trg_subscriptions_hist": [
          "after",
          [
            "delete",
            "update"
          ],
          "row"
        ]
      },
      "grants": {},
      "unsupported": []
    },
    "identity": null
  },
  "subscriptions_hist": {
    "source": {
      "primary_key": [
        "hist_id"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "hist_id"
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
        "hist_id"
      ],
      "primary_key_informational": [],
      "unique": [],
      "unique_nulls_equal": [],
      "foreign_keys": [],
      "foreign_keys_informational": [],
      "not_null": [
        "hist_id"
      ],
      "indexes": [],
      "check_count": 0,
      "checks": [],
      "identity_columns": [
        "hist_id"
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
    "subscriptions": {
      "triggers": [
        "after delete row: target 1, source 0: writes the legacy app makes today behave differently",
        "after update row: target 1, source 0: writes the legacy app makes today behave differently",
        "before update row: target 1, source 0: writes the legacy app makes today behave differently"
      ]
    },
    "subscriptions_hist": {
      "sequences_identity": [
        "target hist_id is identity but source hist_id is not: target-generated keys diverge from the source's"
      ]
    }
  },
  "dictionary": {
    "source": "live",
    "target": "live"
  }
}
```

## Tier 0 findings (4)
- `subscriptions` trigger_extra: after delete row: target 1, source 0: writes the legacy app makes today behave differently
- `subscriptions` trigger_extra: after update row: target 1, source 0: writes the legacy app makes today behave differently
- `subscriptions` trigger_extra: before update row: target 1, source 0: writes the legacy app makes today behave differently
- `subscriptions_hist` identity_extra: target hist_id is identity but source hist_id is not: target-generated keys diverge from the source's

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.SUBSCRIPTIONS": 69,
    "OW_BILLING.SUBSCRIPTIONS_HIST": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "subscriptions_hist.hist_dt",
    "subscriptions_hist.hist_op"
  ]
}
```

## Tier 3 coverage
```json
{
  "subscriptions": {
    "mode": "full_diff",
    "population": 69,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "subscriptions_hist": {
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
