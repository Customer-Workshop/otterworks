# Recon report: unit `p3-audit-archive`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `map-p3-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T17:33:44.753868+00:00
- Cost: `{"source_statements": 10, "source_rows_fetched": 84, "target_statements": 8, "target_rows_fetched": 84, "elapsed_s": 3.656}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 7 | PASS |
| 3 | keyed_diffs | 84 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "ow_tp.bronze.p3_audit_legacy_archive": 82,
    "ow_tp.bronze.p3_audit_legacy_run": 2
  }
}
```

## Tier 3 coverage
```json
{
  "audit_archive": {
    "mode": "full_diff",
    "population": 82,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "audit_archive_run": {
    "mode": "full_diff",
    "population": 2,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
