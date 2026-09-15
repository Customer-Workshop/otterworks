> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-credit-notes`

- **Verdict: PASS**
- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T08:13:36.989788+00:00
- Cost: `{"source_statements": 20, "source_rows_fetched": 21, "target_statements": 16, "target_rows_fetched": 16, "elapsed_s": 1.897}`
- **WARNING: UNVERIFIED schema_parity: credit_notes: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | consistency_window | 1 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 5 | PASS |
| 3 | keyed_diffs | 5 | PASS |
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
    "credit_notes": {
      "source_open": [
        "5",
        "2026-02-02 00:00:00"
      ],
      "source_close": [
        "5",
        "2026-02-02 00:00:00"
      ],
      "target_open": [
        5,
        "2026-02-02 00:00:00"
      ],
      "target_close": [
        5,
        "2026-02-02 00:00:00"
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
    "OW_BILLING.credit_notes": 5
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "credit_notes.id",
    "credit_notes.tenant_id",
    "credit_notes.amount",
    "credit_notes.remaining_amount"
  ]
}
```

## Tier 3 coverage
```json
{
  "credit_notes": {
    "mode": "full_diff",
    "population": 5,
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
  "credit_notes": {
    "ranges": 7,
    "population": 5,
    "fingerprint": "unavailable: every range streamed",
    "mismatched_ranges": 7,
    "keys_streamed": 22,
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
  "credit_notes": {
    "watermark": "issued_on->issued_on",
    "unit": "datetime",
    "source_max": "2026-02-02 00:00:00",
    "target_max": "2026-02-02 00:00:00",
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
    "credit_notes: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed"
  ]
}
```
