# Recon report: unit `p2-finance-close`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `map-p2-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T13:28:35.665192+00:00
- Cost: `{"source_statements": 5, "source_rows_fetched": 11, "target_statements": 4, "target_rows_fetched": 11, "elapsed_s": 3.028}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 6 | PASS |
| 3 | keyed_diffs | 11 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.custbill_legacy_baseline_close": 11
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "custbill_finance_close.total_amount"
  ]
}
```

## Tier 3 coverage
```json
{
  "custbill_finance_close": {
    "mode": "full_diff",
    "population": 11,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
