> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-invoice-header`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T07:28:34.241033+00:00
- Cost: `{"source_statements": 6, "source_rows_fetched": 37500, "target_statements": 5, "target_rows_fetched": 37500, "elapsed_s": 42.301}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 9 | PASS |
| 3 | keyed_diffs | 18750 | PASS |
| 4 | app_level_parity | 1 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.invoice_header": 18750
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoice_header.invoice_id",
    "invoice_header.invoice_no",
    "invoice_header.cust_id",
    "invoice_header.tenant_id",
    "invoice_header.invoice_dt",
    "invoice_header.due_dt",
    "invoice_header.total_amt"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoice_header": {
    "mode": "full_diff",
    "population": 18750,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
