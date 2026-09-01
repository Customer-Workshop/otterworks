# Recon report: unit `U0`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.0`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T05:00:14.939737+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 12 | PASS |
| 3 | keyed_diffs | 105 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "tenants.name",
    "tenants.tax_exempt_yn",
    "plans.code",
    "plans.active_yn",
    "codes.code_type",
    "codes.code_desc"
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
  },
  "codes": {
    "mode": "full_diff",
    "population": 32
  },
  "fixture_meta": {
    "mode": "full_diff",
    "population": 1
  }
}
```
