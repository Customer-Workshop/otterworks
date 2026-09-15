> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-customer-master-hist`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `full`
- Generated: 2026-09-15T08:04:00.726587+00:00
- Cost: `{"source_statements": 6, "source_rows_fetched": 0, "target_statements": 5, "target_rows_fetched": 0, "elapsed_s": 2.897}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 1 | PASS |
| 2 | per_field_aggregates | 158 | PASS |
| 3 | keyed_diffs | 0 | PASS |
| 4 | app_level_parity | 1 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.customer_master_hist": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "customer_master_hist.hist_dt",
    "customer_master_hist.hist_op",
    "customer_master_hist.cust_id",
    "customer_master_hist.tenant_id",
    "customer_master_hist.cust_no",
    "customer_master_hist.cust_name",
    "customer_master_hist.cust_name_upper",
    "customer_master_hist.legal_name",
    "customer_master_hist.dba_name",
    "customer_master_hist.addr_line_1",
    "customer_master_hist.addr_line_2",
    "customer_master_hist.addr_line_3",
    "customer_master_hist.addr_line_4",
    "customer_master_hist.addr_line_5",
    "customer_master_hist.addr_line_6",
    "customer_master_hist.city",
    "customer_master_hist.state_cd",
    "customer_master_hist.zip",
    "customer_master_hist.zip4",
    "customer_master_hist.country_cd",
    "customer_master_hist.mail_addr_line_1",
    "customer_master_hist.mail_addr_line_2",
    "customer_master_hist.mail_addr_line_3",
    "customer_master_hist.mail_addr_line_4",
    "customer_master_hist.mail_addr_line_5",
    "customer_master_hist.mail_addr_line_6",
    "customer_master_hist.mail_city",
    "customer_master_hist.mail_state_cd",
    "customer_master_hist.mail_zip",
    "customer_master_hist.phone1",
    "customer_master_hist.phone2",
    "customer_master_hist.phone3",
    "customer_master_hist.phone4",
    "customer_master_hist.fax",
    "customer_master_hist.email_1",
    "customer_master_hist.email_2",
    "customer_master_hist.email_3",
    "customer_master_hist.signup_dt",
    "customer_master_hist.last_activity_dt",
    "customer_master_hist.last_invoice_dt",
    "customer_master_hist.last_payment_dt",
    "customer_master_hist.terminate_dt",
    "customer_master_hist.tax_exempt_yn",
    "customer_master_hist.credit_hold_yn",
    "customer_master_hist.dunning_exempt_yn",
    "customer_master_hist.vip_yn",
    "customer_master_hist.cur_bal_amt",
    "customer_master_hist.past_due_amt",
    "customer_master_hist.ytd_billed_amt",
    "customer_master_hist.ltd_billed_amt",
    "customer_master_hist.ytd_paid_amt",
    "customer_master_hist.credit_limit_amt",
    "customer_master_hist.related_acct_ids",
    "customer_master_hist.child_acct_ids",
    "customer_master_hist.promo_codes_csv",
    "customer_master_hist.contact_notes",
    "customer_master_hist.legacy_sys_key",
    "customer_master_hist.mainframe_acct_no",
    "customer_master_hist.flag_01",
    "customer_master_hist.flag_02",
    "customer_master_hist.flag_03",
    "customer_master_hist.flag_04",
    "customer_master_hist.flag_05",
    "customer_master_hist.flag_06",
    "customer_master_hist.flag_07",
    "customer_master_hist.flag_08",
    "customer_master_hist.flag_09",
    "customer_master_hist.flag_10",
    "customer_master_hist.flag_11",
    "customer_master_hist.flag_12",
    "customer_master_hist.flag_13",
    "customer_master_hist.flag_14",
    "customer_master_hist.flag_15",
    "customer_master_hist.flag_16",
    "customer_master_hist.flag_17",
    "customer_master_hist.flag_18",
    "customer_master_hist.flag_19",
    "customer_master_hist.flag_20",
    "customer_master_hist.udf_01",
    "customer_master_hist.udf_02",
    "customer_master_hist.udf_03",
    "customer_master_hist.udf_04",
    "customer_master_hist.udf_05",
    "customer_master_hist.udf_06",
    "customer_master_hist.udf_07",
    "customer_master_hist.udf_08",
    "customer_master_hist.udf_09",
    "customer_master_hist.udf_10",
    "customer_master_hist.udf_11",
    "customer_master_hist.udf_12",
    "customer_master_hist.udf_13",
    "customer_master_hist.udf_14",
    "customer_master_hist.udf_15",
    "customer_master_hist.udf_16",
    "customer_master_hist.udf_17",
    "customer_master_hist.udf_18",
    "customer_master_hist.udf_19",
    "customer_master_hist.udf_20",
    "customer_master_hist.udf_21",
    "customer_master_hist.udf_22",
    "customer_master_hist.udf_23",
    "customer_master_hist.udf_24",
    "customer_master_hist.udf_25",
    "customer_master_hist.udf_26",
    "customer_master_hist.udf_27",
    "customer_master_hist.udf_28",
    "customer_master_hist.udf_29",
    "customer_master_hist.udf_30",
    "customer_master_hist.udf_31",
    "customer_master_hist.udf_32",
    "customer_master_hist.udf_33",
    "customer_master_hist.udf_34",
    "customer_master_hist.udf_35",
    "customer_master_hist.udf_36",
    "customer_master_hist.udf_37",
    "customer_master_hist.udf_38",
    "customer_master_hist.udf_39",
    "customer_master_hist.udf_40",
    "customer_master_hist.udf_amt_01",
    "customer_master_hist.udf_amt_02",
    "customer_master_hist.udf_amt_03",
    "customer_master_hist.udf_amt_04",
    "customer_master_hist.udf_amt_05",
    "customer_master_hist.udf_amt_06",
    "customer_master_hist.udf_amt_07",
    "customer_master_hist.udf_amt_08",
    "customer_master_hist.udf_amt_09",
    "customer_master_hist.udf_amt_10",
    "customer_master_hist.udf_dt_01",
    "customer_master_hist.udf_dt_02",
    "customer_master_hist.udf_dt_03",
    "customer_master_hist.udf_dt_04",
    "customer_master_hist.udf_dt_05",
    "customer_master_hist.udf_dt_06",
    "customer_master_hist.udf_dt_07",
    "customer_master_hist.udf_dt_08",
    "customer_master_hist.udf_dt_09",
    "customer_master_hist.udf_dt_10",
    "customer_master_hist.created_by",
    "customer_master_hist.updated_by"
  ]
}
```

## Tier 3 coverage
```json
{
  "customer_master_hist": {
    "mode": "full_diff",
    "population": 0,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
