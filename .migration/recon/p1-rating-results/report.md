> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-rating-results`

- **Verdict: PASS**
- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T10:13:18.361458+00:00
- Cost: `{"source_statements": 18, "source_rows_fetched": 13, "target_statements": 14, "target_rows_fetched": 10, "elapsed_s": 1.709}`
- **WARNING: UNVERIFIED schema_parity: rating_results: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | consistency_window | 1 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 9 | PASS |
| 3 | keyed_diffs | 3 | PASS |
| 5 | pk_set_diff | 1 | PASS |
| 6 | cdc_lag_ordering | 1 | PASS |
| 7 | schema_parity | 0 | PASS |

## Tier 0 coverage
```json
{
  "isolation": {
    "source": "snapshot",
    "target": "repeatable_read"
  },
  "strength": {
    "source": "snapshot",
    "target": "snapshot"
  },
  "markers": {
    "rating_results": {
      "source_open": [
        "3",
        "2026-01-31 00:00:00"
      ],
      "source_close": [
        "3",
        "2026-01-31 00:00:00"
      ],
      "target_open": [
        3,
        "2026-01-31 00:00:00"
      ],
      "target_close": [
        3,
        "2026-01-31 00:00:00"
      ],
      "in_flight_at_open": 0
    }
  }
}
```

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.rating_results": 3
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "rating_results.id",
    "rating_results.period_id",
    "rating_results.subscription_id",
    "rating_results.overage_amount"
  ]
}
```

## Tier 3 coverage
```json
{
  "rating_results": {
    "mode": "full_diff",
    "population": 3,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0,
    "in_flight_rows": 0
  }
}
```

## Tier 5 coverage
```json
{
  "rating_results": {
    "ranges": 5,
    "population": 3,
    "fingerprint": "unavailable: every range streamed",
    "mismatched_ranges": 5,
    "keys_streamed": 14,
    "missing_on_target": 0,
    "extra_on_target": 0,
    "in_flight_missing": 0,
    "in_flight_updates": 0,
    "in_flight_deletes": 0,
    "delete_evidence": {
      "status": "absent",
      "kind": null,
      "applied_position": null,
      "horizon": [
        null,
        null
      ],
      "events": 0,
      "in_flight_deletes": 0,
      "aged_deletes": 0,
      "reinserted": 0,
      "detail": ""
    },
    "rows_ahead_on_target": 0,
    "rows_behind_on_target": 0
  }
}
```

## Tier 6 coverage
```json
{
  "rating_results": {
    "watermark": "created_at->created_at",
    "unit": "datetime",
    "source_max": "2026-01-31 00:00:00",
    "target_max": "2026-01-31 00:00:00",
    "lag_s": 0.0,
    "lag_units": null,
    "in_flight": 0,
    "in_flight_deletes": 0,
    "target_max_from_in_flight_delete": false,
    "rows_ahead_on_target": 0,
    "rows_behind_on_target": 0
  }
}
```

## Tier 7 coverage
```json
{
  "unverified": [
    "rating_results: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed"
  ]
}
```
