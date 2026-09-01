# Recon report: unit `U4`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.1`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T15:36:59.157693+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 15 | PASS |
| 3 | keyed_diffs | 820 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "usage_events.tenant_id",
    "rating_periods.tenant_id",
    "rating_results.period_id",
    "rating_results.subscription_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "usage_events": {
    "mode": "full_diff",
    "population": 814
  },
  "rating_periods": {
    "mode": "full_diff",
    "population": 3
  },
  "rating_results": {
    "mode": "full_diff",
    "population": 3
  }
}
```
