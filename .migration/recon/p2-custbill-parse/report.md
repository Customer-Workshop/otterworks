# Recon report: unit `p2-custbill-parse`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `map-p2-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T13:06:58.852011+00:00
- Cost: `{"source_statements": 5, "source_rows_fetched": 116, "target_statements": 4, "target_rows_fetched": 116, "elapsed_s": 2.462}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 3 | PASS |
| 3 | keyed_diffs | 116 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.custbill_legacy_baseline_psv": 116
  }
}
```

## Tier 3 coverage
```json
{
  "custbill": {
    "mode": "full_diff",
    "population": 116,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
