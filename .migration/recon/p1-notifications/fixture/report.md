> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-notifications`

- **Verdict: PASS**
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T10:33:43.939906+00:00
- Cost: `{"source_statements": 5, "source_rows_fetched": 1, "target_statements": 5, "target_rows_fetched": 1, "elapsed_s": 0.018}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 4 | PASS |
| 3 | keyed_diffs | 1 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.notifications": 1
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "notifications.id",
    "notifications.tenant_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "notifications": {
    "mode": "full_diff",
    "population": 1,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
