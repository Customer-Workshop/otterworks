# Recon report: unit `invoices`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.0.0`
- Tolerance version: `1`
- Generated: 2026-09-01T01:38:00.906939+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 9 | PASS |
| 3 | keyed_diffs | 18750 | PASS |
| 4 | app_level_parity | 2 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoices._id",
    "invoices.invoice_no",
    "invoices.cust_id",
    "invoices.tenant_id",
    "invoices.legacy.invoice_dt",
    "invoices.legacy.due_dt"
  ],
  "sum_not_comparable": [
    "invoices._id",
    "invoices.invoice_no",
    "invoices.cust_id",
    "invoices.tenant_id",
    "invoices.legacy.invoice_dt",
    "invoices.legacy.due_dt"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoices": {
    "mode": "full_diff",
    "population": 18750
  }
}
```
