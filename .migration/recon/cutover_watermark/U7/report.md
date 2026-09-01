# Recon report: unit `U7`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.1`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T18:04:02.908524+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 3 | PASS |
| 3 | keyed_diffs | 0 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "billing_audit_log.module",
    "billing_audit_log.message"
  ]
}
```

## Tier 3 coverage
```json
{
  "billing_audit_log": {
    "mode": "full_diff",
    "population": 0
  }
}
```
