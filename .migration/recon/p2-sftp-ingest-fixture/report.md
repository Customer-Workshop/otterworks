# Recon report: unit `p2-sftp-ingest`

- **Verdict: PASS**
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping version: `map-p2-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T12:18:18.039366+00:00
- Cost: `{"source_statements": 5, "source_rows_fetched": 123, "target_statements": 4, "target_rows_fetched": 123, "elapsed_s": 3.722}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 4 | PASS |
| 3 | keyed_diffs | 123 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.custbill_legacy_baseline_raw": 123
  }
}
```

## Tier 3 coverage
```json
{
  "custbill_raw": {
    "mode": "full_diff",
    "population": 123,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
