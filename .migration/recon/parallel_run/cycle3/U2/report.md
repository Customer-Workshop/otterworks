# Recon report: unit `U2`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.0`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T18:07:52.285370+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 8 | PASS |
| 3 | keyed_diffs | 168713 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoice_feed.invoice_no",
    "invoice_feed.cust_id",
    "invoice_feed.tenant_id",
    "invoice_feed.invoice_dt",
    "invoice_feed.due_dt"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoice_feed": {
    "mode": "full_diff",
    "population": 18750
  },
  "embeds_graded": {
    "invoice_feed.lines": 149963
  }
}
```
