# Recon report: unit `U1`

- **Verdict: FAIL**
- Mode: `live`
- Mapping version: `1.0`
- Tolerance version: `1.0`
- Seed: `0`
- Generated: 2026-09-01T05:49:59.031174+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 311 | FAIL (36 findings) |
| 3 | keyed_diffs | 33333 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "customers.tenant_id",
    "customers.cust_no",
    "customers.cust_name",
    "customers.cust_name_upper",
    "customers.legal_name",
    "customers.dba_name",
    "customers.addr_line_1",
    "customers.addr_line_2",
    "customers.addr_line_3",
    "customers.addr_line_4",
    "customers.addr_line_5",
    "customers.addr_line_6",
    "customers.city",
    "customers.state_cd",
    "customers.zip",
    "customers.zip4",
    "customers.country_cd",
    "customers.mail_addr_line_1",
    "customers.mail_addr_line_2",
    "customers.mail_addr_line_3",
    "customers.mail_addr_line_4",
    "customers.mail_addr_line_5",
    "customers.mail_addr_line_6",
    "customers.mail_city",
    "customers.mail_state_cd",
    "customers.mail_zip",
    "customers.phone1",
    "customers.phone2",
    "customers.phone3",
    "customers.phone4",
    "customers.fax",
    "customers.email_1",
    "customers.email_2",
    "customers.email_3",
    "customers.signup_dt",
    "customers.last_activity_dt",
    "customers.last_invoice_dt",
    "customers.last_payment_dt",
    "customers.terminate_dt",
    "customers.tax_exempt_yn",
    "customers.credit_hold_yn",
    "customers.dunning_exempt_yn",
    "customers.vip_yn",
    "customers.related_acct_ids",
    "customers.child_acct_ids",
    "customers.promo_codes_csv",
    "customers.contact_notes",
    "customers.legacy_sys_key",
    "customers.mainframe_acct_no",
    "customers.flag_01",
    "customers.flag_02",
    "customers.flag_03",
    "customers.flag_04",
    "customers.flag_05",
    "customers.flag_06",
    "customers.flag_07",
    "customers.flag_08",
    "customers.flag_09",
    "customers.flag_10",
    "customers.flag_11",
    "customers.flag_12",
    "customers.flag_13",
    "customers.flag_14",
    "customers.flag_15",
    "customers.flag_16",
    "customers.flag_17",
    "customers.flag_18",
    "customers.flag_19",
    "customers.flag_20",
    "customers.udf_01",
    "customers.udf_02",
    "customers.udf_03",
    "customers.udf_04",
    "customers.udf_05",
    "customers.udf_06",
    "customers.udf_07",
    "customers.udf_08",
    "customers.udf_09",
    "customers.udf_10",
    "customers.udf_11",
    "customers.udf_12",
    "customers.udf_13",
    "customers.udf_14",
    "customers.udf_15",
    "customers.udf_16",
    "customers.udf_17",
    "customers.udf_18",
    "customers.udf_19",
    "customers.udf_20",
    "customers.udf_21",
    "customers.udf_22",
    "customers.udf_23",
    "customers.udf_24",
    "customers.udf_25",
    "customers.udf_26",
    "customers.udf_27",
    "customers.udf_28",
    "customers.udf_29",
    "customers.udf_30",
    "customers.udf_31",
    "customers.udf_32",
    "customers.udf_33",
    "customers.udf_34",
    "customers.udf_35",
    "customers.udf_36",
    "customers.udf_37",
    "customers.udf_38",
    "customers.udf_39",
    "customers.udf_40",
    "customers.udf_dt_01",
    "customers.udf_dt_02",
    "customers.udf_dt_03",
    "customers.udf_dt_04",
    "customers.udf_dt_05",
    "customers.udf_dt_06",
    "customers.udf_dt_07",
    "customers.udf_dt_08",
    "customers.udf_dt_09",
    "customers.udf_dt_10",
    "customers.created_by",
    "customers.updated_by",
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

## Tier 2 findings (36)
- `customers` aggregate_distinct_count: field PHONE3_TYPE_CD->phone3_type_cd | source=0 target=1 | rules=[]
- `customers` aggregate_sum: field PHONE3_TYPE_CD->phone3_type_cd | source=None target=0.0 | rules=[]
- `customers` aggregate_distinct_count: field PHONE4_TYPE_CD->phone4_type_cd | source=0 target=1 | rules=[]
- `customers` aggregate_sum: field PHONE4_TYPE_CD->phone4_type_cd | source=None target=0.0 | rules=[]
- `customers` aggregate_distinct_count: field SUB_STATUS_CD->sub_status_cd | source=2 target=3 | rules=[]
- `customers` aggregate_distinct_count: field TERRITORY_CD->territory_cd | source=0 target=1 | rules=[]
- `customers` aggregate_sum: field TERRITORY_CD->territory_cd | source=None target=0.0 | rules=[]
- `customers` aggregate_distinct_count: field CHANNEL_CD->channel_cd | source=0 target=1 | rules=[]
- `customers` aggregate_sum: field CHANNEL_CD->channel_cd | source=None target=0.0 | rules=[]
- `customers` aggregate_distinct_count: field RATE_CLASS_CD->rate_class_cd | source=0 target=1 | rules=[]
- `customers` aggregate_sum: field RATE_CLASS_CD->rate_class_cd | source=None target=0.0 | rules=[]
- `customers` aggregate_distinct_count: field LTD_BILLED_AMT->ltd_billed_amt | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field LTD_BILLED_AMT->ltd_billed_amt | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field YTD_PAID_AMT->ytd_paid_amt | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field YTD_PAID_AMT->ytd_paid_amt | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field CREDIT_LIMIT_AMT->credit_limit_amt | source=4 target=5 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_01->udf_amt_01 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_01->udf_amt_01 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_02->udf_amt_02 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_02->udf_amt_02 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_03->udf_amt_03 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_03->udf_amt_03 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_04->udf_amt_04 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_04->udf_amt_04 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_05->udf_amt_05 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_05->udf_amt_05 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_06->udf_amt_06 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_06->udf_amt_06 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_07->udf_amt_07 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_07->udf_amt_07 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_08->udf_amt_08 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_08->udf_amt_08 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_09->udf_amt_09 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_09->udf_amt_09 | source=None target=0.0 | rules=['decimal_round']
- `customers` aggregate_distinct_count: field UDF_AMT_10->udf_amt_10 | source=0 target=1 | rules=['decimal_round']
- `customers` aggregate_sum: field UDF_AMT_10->udf_amt_10 | source=None target=0.0 | rules=['decimal_round']

## Tier 3 coverage
```json
{
  "customers": {
    "mode": "full_diff",
    "population": 25000
  },
  "embeds_graded": {
    "customers.attributes": 8333
  },
  "customer_master_hist": {
    "mode": "full_diff",
    "population": 0
  }
}
```
