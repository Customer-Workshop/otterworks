> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-usage-events`

- **Verdict: PASS**
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T07:05:16.353643+00:00
- Cost: `{"source_statements": 8, "source_rows_fetched": 21, "target_statements": 7, "target_rows_fetched": 21, "elapsed_s": 2.842}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 5 | PASS |
| 3 | keyed_diffs | 10 | PASS |
| 4 | app_level_parity | 3 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.usage_events": 10
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "usage_events.id",
    "usage_events.tenant_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "usage_events": {
    "mode": "full_diff",
    "population": 10,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
