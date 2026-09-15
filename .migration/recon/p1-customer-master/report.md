> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-customer-master`

- **Verdict: PASS**
- Mode: `transactional` (both sides live: PASS scoped to the consistency window that held and the target's applied CDC watermark)
- Merge eligible: no (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T08:03:32.680583+00:00
- Cost: `{"source_statements": 79, "source_rows_fetched": 75129, "target_statements": 76, "target_rows_fetched": 75065, "elapsed_s": 73.428}`
- **WARNING: UNVERIFIED schema_parity: customer_master: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | consistency_window | 1 | PASS |
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 155 | PASS |
| 3 | keyed_diffs | 25000 | PASS |
| 4 | app_level_parity | 1 | PASS |
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
    "customer_master": {
      "source_open": [
        "25000",
        "ffffe14d-9edc-f5d9-fac6-18eb4dc16819"
      ],
      "source_close": [
        "25000",
        "ffffe14d-9edc-f5d9-fac6-18eb4dc16819"
      ],
      "target_open": [
        25000,
        "ffffe14d-9edc-f5d9-fac6-18eb4dc16819"
      ],
      "target_close": [
        25000,
        "ffffe14d-9edc-f5d9-fac6-18eb4dc16819"
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
    "OW_BILLING.customer_master": 25000
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "customer_master.cust_id",
    "customer_master.tenant_id",
    "customer_master.cust_no",
    "customer_master.cust_name",
    "customer_master.cust_name_upper",
    "customer_master.legal_name",
    "customer_master.dba_name",
    "customer_master.addr_line_1",
    "customer_master.addr_line_2",
    "customer_master.addr_line_3",
    "customer_master.addr_line_4",
    "customer_master.addr_line_5",
    "customer_master.addr_line_6",
    "customer_master.city",
    "customer_master.state_cd",
    "customer_master.zip",
    "customer_master.zip4",
    "customer_master.country_cd",
    "customer_master.mail_addr_line_1",
    "customer_master.mail_addr_line_2",
    "customer_master.mail_addr_line_3",
    "customer_master.mail_addr_line_4",
    "customer_master.mail_addr_line_5",
    "customer_master.mail_addr_line_6",
    "customer_master.mail_city",
    "customer_master.mail_state_cd",
    "customer_master.mail_zip",
    "customer_master.phone1",
    "customer_master.phone2",
    "customer_master.phone3",
    "customer_master.phone4",
    "customer_master.fax",
    "customer_master.email_1",
    "customer_master.email_2",
    "customer_master.email_3",
    "customer_master.signup_dt",
    "customer_master.last_activity_dt",
    "customer_master.last_invoice_dt",
    "customer_master.last_payment_dt",
    "customer_master.terminate_dt",
    "customer_master.tax_exempt_yn",
    "customer_master.credit_hold_yn",
    "customer_master.dunning_exempt_yn",
    "customer_master.vip_yn",
    "customer_master.cur_bal_amt",
    "customer_master.past_due_amt",
    "customer_master.ytd_billed_amt",
    "customer_master.ltd_billed_amt",
    "customer_master.ytd_paid_amt",
    "customer_master.credit_limit_amt",
    "customer_master.related_acct_ids",
    "customer_master.child_acct_ids",
    "customer_master.promo_codes_csv",
    "customer_master.contact_notes",
    "customer_master.legacy_sys_key",
    "customer_master.mainframe_acct_no",
    "customer_master.flag_01",
    "customer_master.flag_02",
    "customer_master.flag_03",
    "customer_master.flag_04",
    "customer_master.flag_05",
    "customer_master.flag_06",
    "customer_master.flag_07",
    "customer_master.flag_08",
    "customer_master.flag_09",
    "customer_master.flag_10",
    "customer_master.flag_11",
    "customer_master.flag_12",
    "customer_master.flag_13",
    "customer_master.flag_14",
    "customer_master.flag_15",
    "customer_master.flag_16",
    "customer_master.flag_17",
    "customer_master.flag_18",
    "customer_master.flag_19",
    "customer_master.flag_20",
    "customer_master.udf_01",
    "customer_master.udf_02",
    "customer_master.udf_03",
    "customer_master.udf_04",
    "customer_master.udf_05",
    "customer_master.udf_06",
    "customer_master.udf_07",
    "customer_master.udf_08",
    "customer_master.udf_09",
    "customer_master.udf_10",
    "customer_master.udf_11",
    "customer_master.udf_12",
    "customer_master.udf_13",
    "customer_master.udf_14",
    "customer_master.udf_15",
    "customer_master.udf_16",
    "customer_master.udf_17",
    "customer_master.udf_18",
    "customer_master.udf_19",
    "customer_master.udf_20",
    "customer_master.udf_21",
    "customer_master.udf_22",
    "customer_master.udf_23",
    "customer_master.udf_24",
    "customer_master.udf_25",
    "customer_master.udf_26",
    "customer_master.udf_27",
    "customer_master.udf_28",
    "customer_master.udf_29",
    "customer_master.udf_30",
    "customer_master.udf_31",
    "customer_master.udf_32",
    "customer_master.udf_33",
    "customer_master.udf_34",
    "customer_master.udf_35",
    "customer_master.udf_36",
    "customer_master.udf_37",
    "customer_master.udf_38",
    "customer_master.udf_39",
    "customer_master.udf_40",
    "customer_master.udf_amt_01",
    "customer_master.udf_amt_02",
    "customer_master.udf_amt_03",
    "customer_master.udf_amt_04",
    "customer_master.udf_amt_05",
    "customer_master.udf_amt_06",
    "customer_master.udf_amt_07",
    "customer_master.udf_amt_08",
    "customer_master.udf_amt_09",
    "customer_master.udf_amt_10",
    "customer_master.udf_dt_01",
    "customer_master.udf_dt_02",
    "customer_master.udf_dt_03",
    "customer_master.udf_dt_04",
    "customer_master.udf_dt_05",
    "customer_master.udf_dt_06",
    "customer_master.udf_dt_07",
    "customer_master.udf_dt_08",
    "customer_master.udf_dt_09",
    "customer_master.udf_dt_10",
    "customer_master.created_by",
    "customer_master.updated_by"
  ]
}
```

## Tier 3 coverage
```json
{
  "customer_master": {
    "mode": "full_diff",
    "population": 25000,
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
  "customer_master": {
    "ranges": 66,
    "population": 25000,
    "fingerprint": "unavailable: every range streamed",
    "mismatched_ranges": 66,
    "keys_streamed": 50130,
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
  "customer_master": {
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
    "customer_master: OracleJdbcSourceAdapter reads no constraint metadata: tiers 5-7 are part of the degraded surface and are reported as unverified, not guessed"
  ]
}
```
