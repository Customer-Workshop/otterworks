# Recon report: unit `pkg_invoicing`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-pkg_invoicing-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `full`
- Generated: 2026-09-28T00:35:23.071747+00:00

## Routine parity: 11 proven, 0 unproven, 0 failed

- Cost: `{"source_statements": 40, "source_rows_fetched": 10, "target_statements": 29, "target_rows_fetched": 10, "elapsed_s": 3.303}`
- Rerun proof: fresh `pass`, evolved `unsupported` (evolved pre_shape equals the fresh shape: nothing evolved, so the run proves only what fresh proved)

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 3 | PASS |
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 19 | PASS |
| 3 | keyed_diffs | 10 | PASS |

## Tier 0 coverage
```json
{
  "foreign_keys_out_of_scope": [
    "invoices: ('period_id',) -> ow_billing.rating_periods",
    "invoices: ('tenant_id',) -> ow_billing.tenants",
    "invoices: target FK ('period_id',) -> billing.rating_periods",
    "invoices: target FK ('tenant_id',) -> billing.tenants",
    "credit_notes: ('tenant_id',) -> ow_billing.tenants",
    "credit_notes: target FK ('tenant_id',) -> billing.tenants"
  ],
  "invoices": {
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
        "issued_at",
        "period_id",
        "status_cd",
        "subtotal",
        "tax",
        "tenant_id",
        "total"
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
        "issued_at",
        "period_id",
        "status_cd",
        "subtotal",
        "tax",
        "tenant_id",
        "total"
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
  "invoice_lines": {
    "source": {
      "primary_key": [
        "id"
      ],
      "primary_key_informational": [],
      "unique": [
        [
          "invoice_id",
          "line_no"
        ]
      ],
      "unique_nulls_equal": [],
      "foreign_keys": [
        [
          [
            "invoice_id"
          ],
          "ow_billing.invoices",
          [
            "id"
          ],
          "no action",
          "cascade"
        ]
      ],
      "foreign_keys_informational": [],
      "not_null": [
        "amount",
        "description",
        "id",
        "invoice_id",
        "line_no",
        "line_type"
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
          "invoice_id",
          "line_no"
        ]
      ],
      "unique_nulls_equal": [],
      "foreign_keys": [
        [
          [
            "invoice_id"
          ],
          "billing.invoices",
          [
            "id"
          ],
          "no action",
          "cascade"
        ]
      ],
      "foreign_keys_informational": [],
      "not_null": [
        "amount",
        "description",
        "id",
        "invoice_id",
        "line_no",
        "line_type"
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
  "credit_notes": {
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
        "amount",
        "id",
        "issued_on",
        "remaining_amount",
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
        "amount",
        "id",
        "issued_on",
        "remaining_amount",
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
    "OW_BILLING.INVOICES": 3,
    "OW_BILLING.INVOICE_LINES": 2,
    "OW_BILLING.CREDIT_NOTES": 5
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoice_lines.line_type",
    "invoice_lines.description"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoices": {
    "mode": "full_diff",
    "population": 3,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "invoice_lines": {
    "mode": "full_diff",
    "population": 2,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "credit_notes": {
    "mode": "full_diff",
    "population": 5,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
