# Recon report: unit `p3-analytics-daily`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `map-p3-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T16:15:12.529964+00:00
- Cost: `{"source_statements": 20, "source_rows_fetched": 224, "target_statements": 16, "target_rows_fetched": 224, "elapsed_s": 7.815}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 25 | PASS |
| 3 | keyed_diffs | 224 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.p3_analytics_legacy_baseline": 1,
    "ow_tp.bronze.p3_analytics_legacy_top_users": 13,
    "ow_tp.bronze.p3_analytics_legacy_hourly": 129,
    "ow_tp.bronze.p3_analytics_legacy_top_user_actions": 81
  }
}
```

## Tier 3 coverage
```json
{
  "analytics_daily_summary": {
    "mode": "full_diff",
    "population": 1,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "analytics_daily_top_users": {
    "mode": "full_diff",
    "population": 13,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "analytics_daily_hourly": {
    "mode": "full_diff",
    "population": 129,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "analytics_daily_top_user_actions": {
    "mode": "full_diff",
    "population": 81,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
