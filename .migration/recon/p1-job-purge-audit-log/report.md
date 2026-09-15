> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-job-purge-audit-log`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `sampled`
- Generated: 2026-09-15T08:15:33.231138+00:00
- Cost: `{"source_statements": 6, "source_rows_fetched": 0, "target_statements": 3, "target_rows_fetched": 0, "elapsed_s": 0.996}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 4 | PASS |
| 3 | keyed_diffs | 0 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.billing_audit_log": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "billing_audit_log.module",
    "billing_audit_log.message"
  ]
}
```

## Tier 3 coverage
```json
{
  "billing_audit_log": {
    "mode": "stratified_sample",
    "sampling": "stratified",
    "strata": 0,
    "population": 0,
    "sampled": 0,
    "coverage": 1.0,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
