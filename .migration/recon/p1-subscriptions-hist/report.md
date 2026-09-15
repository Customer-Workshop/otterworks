> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-subscriptions-hist`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T08:04:07.515786+00:00
- Cost: `{"source_statements": 5, "source_rows_fetched": 0, "target_statements": 4, "target_rows_fetched": 0, "elapsed_s": 1.727}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 10 | PASS |
| 3 | keyed_diffs | 0 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.subscriptions_hist": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "subscriptions_hist.hist_dt",
    "subscriptions_hist.hist_op",
    "subscriptions_hist.id",
    "subscriptions_hist.tenant_id",
    "subscriptions_hist.plan_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "subscriptions_hist": {
    "mode": "full_diff",
    "population": 0,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
