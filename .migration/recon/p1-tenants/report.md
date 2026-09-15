> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-tenants`

- **Verdict: PASS**
- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T07:00:48.814315+00:00
- Cost: `{"source_statements": 78, "source_rows_fetched": 267, "target_statements": 75, "target_rows_fetched": 203, "elapsed_s": 8.652}`
- **WARNING: UNVERIFIED schema_parity: tenants: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | consistency_window | 1 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 4 | PASS |
| 3 | keyed_diffs | 69 | PASS |
| 5 | pk_set_diff | 1 | PASS |
| 6 | cdc_lag_ordering | 0 | PASS |
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
    "tenants": {
      "source_open": [
        "69",
        "fd52ea22-b475-5783-4a84-900e36eb5289"
      ],
      "source_close": [
        "69",
        "fd52ea22-b475-5783-4a84-900e36eb5289"
      ],
      "target_open": [
        69,
        "fd52ea22-b475-5783-4a84-900e36eb5289"
      ],
      "target_close": [
        69,
        "fd52ea22-b475-5783-4a84-900e36eb5289"
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
    "OW_BILLING.tenants": 69
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "tenants.id",
    "tenants.name",
    "tenants.tax_exempt_yn"
  ]
}
```

## Tier 3 coverage
```json
{
  "tenants": {
    "mode": "full_diff",
    "population": 69,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```

## Tier 5 coverage
```json
{
  "tenants": {
    "ranges": 66,
    "population": 69,
    "fingerprint": "unavailable: every range streamed",
    "mismatched_ranges": 66,
    "keys_streamed": 268,
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
  "tenants": {
    "watermark": null,
    "note": "no watermark declared: the window markers alone prove stillness",
    "in_flight_deletes": 0
  }
}
```

## Tier 7 coverage
```json
{
  "unverified": [
    "tenants: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed"
  ]
}
```
