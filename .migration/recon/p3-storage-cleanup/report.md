# Recon report: unit `p3-storage-cleanup`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `map-p3-v1`
- Tolerance version: `v1`
- Seed: `0` | Params: `{'batch': 'p3probe'}`
- Tier 3 depth: `full`
- Generated: 2026-09-15T17:17:04.177583+00:00
- Cost: `{"source_statements": 5, "source_rows_fetched": 17, "target_statements": 4, "target_rows_fetched": 17, "elapsed_s": 3.134}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 2 | PASS |
| 3 | keyed_diffs | 17 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.p3_cleanup_legacy_delete_set": 17
  }
}
```

## Tier 3 coverage
```json
{
  "storage_cleanup_candidates": {
    "mode": "full_diff",
    "population": 17,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
