# Recon report: unit `U4-usage`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1`
- Tolerance version: `1`
- Seed: `714559852`
- Generated: 2026-09-15T05:25:03.256606+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 6 | PASS |
| 3 | keyed_diffs | 820 | PASS |
| 4 | app_level_parity | 4 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "USAGE_EVENTS": 814,
    "RATING_PERIODS": 3
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "usage_events.tenantId",
    "usage_events.units",
    "rating_periods.tenantId"
  ]
}
```

## Tier 3 coverage
```json
{
  "usage_events": {
    "mode": "full_diff",
    "population": 814,
    "duplicate_source_key_count": 0
  },
  "rating_periods": {
    "mode": "full_diff",
    "population": 3,
    "duplicate_source_key_count": 0
  },
  "embeds_graded": {
    "rating_periods.results": 3
  }
}
```
