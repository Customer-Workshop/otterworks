> **DEGRADED - not an official harness verdict.** The Oracle side is read over JDBC with a repo-local adapter (reason: `d10_01_denied`); `official_verdict` is false. Merge eligibility below is the data verdict under the owner's STOP C exception, not the harness certifying the source. See DEGRADED.md.

# Recon report: unit `p1-cdc-transport`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges) - degraded, see DEGRADED.md
- Mapping version: `map-p1-v1`
- Tolerance version: `v1`
- Seed: `0`
- Tier 3 depth: `threshold`
- Generated: 2026-09-15T06:40:08.802469+00:00
- Cost: `{"source_statements": 15, "source_rows_fetched": 193750, "target_statements": 12, "target_rows_fetched": 193750, "elapsed_s": 546.123}`

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 184 | PASS |
| 3 | keyed_diffs | 193750 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.customer_master": 25000,
    "OW_BILLING.invoice_header": 18750,
    "OW_BILLING.invoice_line": 150000
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
    "customer_master.updated_by",
    "invoice_header.invoice_id",
    "invoice_header.invoice_no",
    "invoice_header.cust_id",
    "invoice_header.tenant_id",
    "invoice_header.invoice_dt",
    "invoice_header.due_dt",
    "invoice_header.total_amt",
    "invoice_line.line_id",
    "invoice_line.invoice_no",
    "invoice_line.invoice_id",
    "invoice_line.cust_id",
    "invoice_line.cust_no",
    "invoice_line.cust_name",
    "invoice_line.tenant_id",
    "invoice_line.item_desc",
    "invoice_line.qty",
    "invoice_line.unit_price",
    "invoice_line.amount",
    "invoice_line.tax_amt",
    "invoice_line.invoice_dt",
    "invoice_line.service_period",
    "invoice_line.posted_yn",
    "invoice_line.gl_acct_csv",
    "invoice_line.src_system"
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
  },
  "invoice_header": {
    "mode": "full_diff",
    "population": 18750,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "invoice_line": {
    "mode": "full_diff",
    "population": 150000,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
