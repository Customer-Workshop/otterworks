# Recon report: unit `p3-user-activity`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `map-p3-v1`
- Tolerance version: `v1`
- Seed: `0` | Params: `{'batch': 'p3probe', 'run_date': '2026-09-15'}`
- Tier 3 depth: `full`
- Generated: 2026-09-15T21:51:12.454922+00:00
- Cost: `{"source_statements": 20, "source_rows_fetched": 3141, "target_statements": 16, "target_rows_fetched": 3141, "elapsed_s": 13.737}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 29 | PASS |
| 3 | keyed_diffs | 3141 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.p3_user_activity_legacy_report": 1,
    "ow_tp.bronze.p3_user_activity_legacy_days": 30,
    "ow_tp.bronze.p3_user_activity_legacy_users": 500,
    "ow_tp.bronze.p3_user_activity_legacy_user_actions": 2610
  }
}
```

## Tier 3 coverage
```json
{
  "user_activity_report": {
    "mode": "full_diff",
    "population": 1,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "user_activity_report_days": {
    "mode": "full_diff",
    "population": 30,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "user_activity_user_summary": {
    "mode": "full_diff",
    "population": 500,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "user_activity_user_actions": {
    "mode": "full_diff",
    "population": 2610,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
