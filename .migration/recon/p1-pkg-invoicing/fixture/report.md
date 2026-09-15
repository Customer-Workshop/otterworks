> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-pkg-invoicing`

- **Verdict: PASS**
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T11:33:29.961726+00:00
- Cost: `{"source_statements": 10, "source_rows_fetched": 5, "target_statements": 9, "target_rows_fetched": 5, "elapsed_s": 0.044}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 14 | PASS |
| 3 | keyed_diffs | 5 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.invoices": 3,
    "OW_BILLING.invoice_lines": 2
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoices.id",
    "invoices.tenant_id",
    "invoices.period_id",
    "invoices.subtotal",
    "invoices.tax",
    "invoices.total",
    "invoice_lines.id",
    "invoice_lines.invoice_id",
    "invoice_lines.line_type",
    "invoice_lines.description",
    "invoice_lines.amount"
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
  }
}
```
