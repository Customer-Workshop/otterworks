# Recon report: unit `w0-b01`

- **Verdict: PASS** (values redacted)
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1.0.0`
- Tolerance version: `1.0.0`
- Seed: `20260926`
- Generated: 2026-09-26T17:19:32.174001+00:00
- 10 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 6 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 8 | PASS |
| 3 | keyed_diffs | 105 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "codes": 32,
    "tenants": 70,
    "plans": 3
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "codes.codeType",
    "codes.codeDesc",
    "tenants.id",
    "tenants.name",
    "tenants.taxExemptYn",
    "plans.id",
    "plans.code",
    "plans.monthlyFee",
    "plans.overageRate",
    "plans.activeYn"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "codes.codeType",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "codes.codeDesc",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "tenants.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "tenants.name",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "plans.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "plans.code",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    }
  ],
  "fields_fully_deferred": 6
}
```

## Tier 3 coverage
```json
{
  "codes": {
    "mode": "full_diff",
    "population": 32,
    "duplicate_source_key_count": 0
  },
  "tenants": {
    "mode": "full_diff",
    "population": 70,
    "duplicate_source_key_count": 0
  },
  "plans": {
    "mode": "full_diff",
    "population": 3,
    "duplicate_source_key_count": 0
  }
}
```
