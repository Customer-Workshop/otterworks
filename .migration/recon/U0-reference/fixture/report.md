# Recon report: unit `U0-reference`

- **Verdict: PASS** (values redacted)
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging) | Target: `local` (local target: NOT a merge verdict)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping version: `map-1` (sha256 `e6fda9603553`)
- Tolerance version: `1` (sha256 `03b3c6cc0bc6`)
- Collections: `codes`, `tenants`, `plans`
- Seed: `1`
- Generated: 2026-09-29T18:44:56.990249+00:00
- 8 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 6 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 6 | PASS |
| 3 | keyed_diffs | 112 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "codes": 32,
    "tenants": 77,
    "plans": 3
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "codes.code_type",
    "codes.code_desc",
    "tenants.name",
    "tenants.tax_exempt_yn",
    "plans.code",
    "plans.monthly_fee",
    "plans.overage_rate",
    "plans.active_yn"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "codes.code_type",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "codes.code_desc",
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
      "field": "tenants.tax_exempt_yn",
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
    },
    {
      "field": "plans.active_yn",
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
    "population": 77,
    "duplicate_source_key_count": 0
  },
  "plans": {
    "mode": "full_diff",
    "population": 3,
    "duplicate_source_key_count": 0
  }
}
```
