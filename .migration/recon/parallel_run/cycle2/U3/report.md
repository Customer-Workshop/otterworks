# Recon report: unit `U3`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.2`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T18:05:58.654520+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 15 | PASS |
| 3 | keyed_diffs | 69 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "subscriptions.tenant_id",
    "subscriptions.plan_id",
    "subscriptions.ends_on",
    "subscriptions.suspended_on",
    "subscriptions_hist.hist_dt",
    "subscriptions_hist.hist_op",
    "subscriptions_hist.id",
    "subscriptions_hist.tenant_id",
    "subscriptions_hist.plan_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "subscriptions": {
    "mode": "full_diff",
    "population": 69
  },
  "subscriptions_hist": {
    "mode": "full_diff",
    "population": 0
  }
}
```
