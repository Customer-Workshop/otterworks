> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-invoice-line`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T07:39:01.490419+00:00
- Cost: `{"source_statements": 6, "source_rows_fetched": 300000, "target_statements": 5, "target_rows_fetched": 300000, "elapsed_s": 664.653}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 20 | PASS |
| 3 | keyed_diffs | 150000 | PASS |
| 4 | app_level_parity | 1 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.invoice_line": 150000
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoice_line.line_id",
    "invoice_line.invoice_no",
    "invoice_line.invoice_id",
    "invoice_line.cust_id",
    "invoice_line.cust_no",
    "invoice_line.cust_name",
    "invoice_line.tenant_id",
    "invoice_line.item_desc",
    "invoice_line.qty",
    "invoice_line.unit_price",
    "invoice_line.amount",
    "invoice_line.tax_amt",
    "invoice_line.invoice_dt",
    "invoice_line.service_period",
    "invoice_line.posted_yn",
    "invoice_line.gl_acct_csv",
    "invoice_line.src_system"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoice_line": {
    "mode": "full_diff",
    "population": 150000,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
