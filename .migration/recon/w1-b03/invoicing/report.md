# Recon report: unit `w1-b03`

- **Verdict: PASS** (values redacted)
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1.0.0`
- Tolerance version: `1.0.0`
- Seed: `20260926`
- Generated: 2026-09-26T17:37:39.789525+00:00
- 12 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 5 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 8 | PASS |
| 3 | keyed_diffs | 13 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "invoices": 4,
    "credit_notes": 5
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoices.id",
    "invoices.tenantId",
    "invoices.periodId",
    "invoices.issuedAt",
    "invoices.subtotal",
    "invoices.tax",
    "invoices.total",
    "credit_notes.id",
    "credit_notes.tenantId",
    "credit_notes.issuedOn",
    "credit_notes.amount",
    "credit_notes.remainingAmount"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "invoices.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoices.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoices.periodId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "credit_notes.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "credit_notes.tenantId",
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
  "invoices": {
    "mode": "full_diff",
    "population": 4,
    "duplicate_source_key_count": 0
  },
  "embeds_graded": {
    "invoices.lines": 4
  },
  "credit_notes": {
    "mode": "full_diff",
    "population": 5,
    "duplicate_source_key_count": 0
  }
}
```
