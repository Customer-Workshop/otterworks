# Recon report: unit `p3-usage-rollup`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `map-p3-v1`
- Tolerance version: `v1`
- Seed: `0` | Params: `{'batch': 'p3probe'}`
- Tier 3 depth: `full`
- Generated: 2026-09-15T18:00:44.900209+00:00
- Cost: `{"source_statements": 5, "source_rows_fetched": 7, "target_statements": 4, "target_rows_fetched": 7, "elapsed_s": 2.195}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 12 | PASS |
| 3 | keyed_diffs | 7 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.p3_usage_legacy_rollup": 7
  }
}
```

## Tier 3 coverage
```json
{
  "usage_rollup": {
    "mode": "full_diff",
    "population": 7,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
