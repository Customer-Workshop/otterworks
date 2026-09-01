# Recon report: unit `U6`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.2`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T18:04:01.077371+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 10 | PASS |
| 3 | keyed_diffs | 7 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoices.tenant_id",
    "invoices.period_id",
    "notifications.tenant_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoices": {
    "mode": "full_diff",
    "population": 3
  },
  "embeds_graded": {
    "invoices.lines": 2,
    "invoices.dunning_attempts": 1
  },
  "notifications": {
    "mode": "full_diff",
    "population": 1
  }
}
```
