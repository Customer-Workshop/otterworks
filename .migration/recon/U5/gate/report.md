# Recon report: unit `U5`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.2`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T16:14:31.658578+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 11 | PASS |
| 3 | keyed_diffs | 10 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoices.tenant_id",
    "invoices.period_id",
    "credit_notes.tenant_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoices": {
    "mode": "full_diff",
    "population": 3
  },
  "embeds_graded": {
    "invoices.lines": 2
  },
  "credit_notes": {
    "mode": "full_diff",
    "population": 5
  }
}
```
