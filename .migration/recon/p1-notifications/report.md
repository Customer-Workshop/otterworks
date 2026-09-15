> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-notifications`

- **Verdict: PASS**
- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T08:56:39.566590+00:00
- Cost: `{"source_statements": 16, "source_rows_fetched": 5, "target_statements": 12, "target_rows_fetched": 4, "elapsed_s": 1.17}`
- **WARNING: UNVERIFIED schema_parity: notifications: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | consistency_window | 1 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 4 | PASS |
| 3 | keyed_diffs | 1 | PASS |
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
    "notifications": {
      "source_open": [
        "1",
        "2026-02-16 09:00:00"
      ],
      "source_close": [
        "1",
        "2026-02-16 09:00:00"
      ],
      "target_open": [
        1,
        "2026-02-16 09:00:00"
      ],
      "target_close": [
        1,
        "2026-02-16 09:00:00"
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
    "OW_BILLING.notifications": 1
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "notifications.id",
    "notifications.tenant_id"
  ]
}
```

## Tier 3 coverage
```json
{
  "notifications": {
    "mode": "full_diff",
    "population": 1,
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
  "notifications": {
    "ranges": 3,
    "population": 1,
    "fingerprint": "unavailable: every range streamed",
    "mismatched_ranges": 3,
    "keys_streamed": 6,
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
  "notifications": {
    "watermark": "sent_at->sent_at",
    "unit": "datetime",
    "source_max": "2026-02-16 09:00:00",
    "target_max": "2026-02-16 09:00:00",
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
    "notifications: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed"
  ]
}
```
