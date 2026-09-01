# Recon report: unit `U0-core`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.0`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T04:12:15.442902+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 9 | PASS |
| 3 | keyed_diffs | 72 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "tenants.name",
    "tenants.tax_exempt_yn",
    "plans.code",
    "plans.active_yn"
  ]
}
```

## Tier 3 coverage
```json
{
  "tenants": {
    "mode": "full_diff",
    "population": 69
  },
  "plans": {
    "mode": "full_diff",
    "population": 3
  }
}
```
