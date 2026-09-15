> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-pkg-rating`

- **Verdict: PASS**
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T11:24:38.171624+00:00
- Cost: `{"source_statements": 12, "source_rows_fetched": 244, "target_statements": 11, "target_rows_fetched": 244, "elapsed_s": 0.062}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 13 | PASS |
| 3 | keyed_diffs | 6 | PASS |
| 4 | app_level_parity | 2 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.rating_periods": 3,
    "OW_BILLING.rating_results": 3
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "rating_periods.id",
    "rating_periods.tenant_id",
    "rating_results.id",
    "rating_results.period_id",
    "rating_results.subscription_id",
    "rating_results.overage_amount"
  ]
}
```

## Tier 3 coverage
```json
{
  "rating_periods": {
    "mode": "full_diff",
    "population": 3,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "rating_results": {
    "mode": "full_diff",
    "population": 3,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
