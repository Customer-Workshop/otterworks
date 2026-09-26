# Recon report: unit `w1-b03`

- **Verdict: PASS** (values redacted)
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1.0.0`
- Tolerance version: `1.0.0`
- Seed: `20260926`
- Generated: 2026-09-26T17:37:53.657409+00:00
- 7 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 5 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 5 | PASS |
| 3 | keyed_diffs | 2 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "dunning_attempts": 1,
    "notifications": 1
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "dunning_attempts.id",
    "dunning_attempts.tenantId",
    "dunning_attempts.invoiceId",
    "dunning_attempts.scheduledFor",
    "notifications.id",
    "notifications.tenantId",
    "notifications.sentAt"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "dunning_attempts.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "dunning_attempts.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "dunning_attempts.invoiceId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "notifications.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "notifications.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    }
  ],
  "fields_fully_deferred": 5
}
```

## Tier 3 coverage
```json
{
  "dunning_attempts": {
    "mode": "full_diff",
    "population": 1,
    "duplicate_source_key_count": 0
  },
  "notifications": {
    "mode": "full_diff",
    "population": 1,
    "duplicate_source_key_count": 0
  }
}
```
