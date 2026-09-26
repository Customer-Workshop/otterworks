# Recon report: unit `w1-b03`

- **Verdict: PASS** (values redacted)
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1.0.0`
- Tolerance version: `1.0.0`
- Seed: `20260926`
- Generated: 2026-09-26T17:37:25.238948+00:00
- 13 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 7 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 7 | PASS |
| 3 | keyed_diffs | 881 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "subscriptions": 70,
    "usage_events": 805,
    "rating_periods": 3
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "subscriptions.id",
    "subscriptions.tenantId",
    "subscriptions.planId",
    "subscriptions.startsOn",
    "subscriptions.endsOn",
    "subscriptions.suspendedOn",
    "usage_events.id",
    "usage_events.tenantId",
    "usage_events.occurredAt",
    "rating_periods.id",
    "rating_periods.tenantId",
    "rating_periods.periodStart",
    "rating_periods.periodEnd"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "subscriptions.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions.planId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "usage_events.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "usage_events.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "rating_periods.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "rating_periods.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    }
  ],
  "fields_fully_deferred": 9
}
```

## Tier 3 coverage
```json
{
  "subscriptions": {
    "mode": "full_diff",
    "population": 70,
    "duplicate_source_key_count": 0
  },
  "usage_events": {
    "mode": "full_diff",
    "population": 805,
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
