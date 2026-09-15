# Recon report: unit `U3-invoices`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1`
- Tolerance version: `1`
- Seed: `714559852`
- Generated: 2026-09-15T05:40:04.699317+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 6 | PASS |
| 2 | per_field_aggregates | 21 | PASS |
| 3 | keyed_diffs | 168756 | PASS |
| 4 | app_level_parity | 17 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "INVOICE_HEADER": 18750,
    "INVOICES": 3,
    "INVOICE_LINE": 37
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoices.invoiceNo",
    "invoices.tenantId",
    "invoices.customer.id",
    "invoices.totals.total",
    "invoices.legacy.batchNo",
    "invoices.tenantId",
    "invoices.periodId",
    "invoices.totals.subtotal",
    "invoices.totals.tax",
    "invoices.totals.total",
    "invoice_lines_orphaned.invoiceId",
    "invoice_lines_orphaned.lineNo",
    "invoice_lines_orphaned.type",
    "invoice_lines_orphaned.description",
    "invoice_lines_orphaned.qty",
    "invoice_lines_orphaned.unitPrice",
    "invoice_lines_orphaned.amount",
    "invoice_lines_orphaned.taxAmt",
    "invoice_lines_orphaned.batchNo",
    "invoice_lines_orphaned.srcSystem"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoices": {
    "mode": "full_diff",
    "population": 3,
    "duplicate_source_key_count": 0
  },
  "embeds_graded": {
    "invoices.lines": 2,
    "invoices.dunning": 1
  },
  "invoice_lines_orphaned": {
    "mode": "full_diff",
    "population": 37,
    "duplicate_source_key_count": 0
  }
}
```
