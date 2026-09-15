# Recon report: unit `U5-ancillary`

- **Verdict: PASS**
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping version: `1`
- Tolerance version: `1`
- Seed: `714559852`
- Generated: 2026-09-15T05:24:32.867202+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 9 | PASS |
| 3 | keyed_diffs | 6 | PASS |
| 4 | app_level_parity | 6 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "CREDIT_NOTES": 5,
    "NOTIFICATIONS": 1,
    "BILLING_AUDIT_LOG": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "credit_notes.tenantId",
    "credit_notes.amount",
    "credit_notes.remainingAmount",
    "notifications.tenantId",
    "audit_log.module",
    "audit_log.message"
  ]
}
```

## Tier 3 coverage
```json
{
  "credit_notes": {
    "mode": "full_diff",
    "population": 5,
    "duplicate_source_key_count": 0
  },
  "notifications": {
    "mode": "full_diff",
    "population": 1,
    "duplicate_source_key_count": 0
  },
  "audit_log": {
    "mode": "full_diff",
    "population": 0,
    "duplicate_source_key_count": 0
  }
}
```
