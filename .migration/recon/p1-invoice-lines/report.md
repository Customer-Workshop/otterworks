> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-invoice-lines`

- **Verdict: PASS**
- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T10:15:20.174155+00:00
- Cost: `{"source_statements": 16, "source_rows_fetched": 9, "target_statements": 13, "target_rows_fetched": 7, "elapsed_s": 1.399}`
- **WARNING: UNVERIFIED schema_parity: invoice_lines: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | consistency_window | 1 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 6 | PASS |
| 3 | keyed_diffs | 2 | PASS |
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
    "invoice_lines": {
      "source_open": [
        "2",
        "a0000000-0000-0000-0000-000000000002"
      ],
      "source_close": [
        "2",
        "a0000000-0000-0000-0000-000000000002"
      ],
      "target_open": [
        2,
        "a0000000-0000-0000-0000-000000000002"
      ],
      "target_close": [
        2,
        "a0000000-0000-0000-0000-000000000002"
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
    "OW_BILLING.invoice_lines": 2
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoice_lines.id",
    "invoice_lines.invoice_id",
    "invoice_lines.line_type",
    "invoice_lines.description",
    "invoice_lines.amount"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoice_lines": {
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

## Tier 5 coverage
```json
{
  "invoice_lines": {
    "ranges": 4,
    "population": 2,
    "fingerprint": "unavailable: every range streamed",
    "mismatched_ranges": 4,
    "keys_streamed": 10,
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
  "invoice_lines": {
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
    "invoice_lines: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed"
  ]
}
```
