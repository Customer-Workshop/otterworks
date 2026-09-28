# Recon report: unit `custbill_lakeflow`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: no (fixture/continuous evidence never merges)
- Merge authority: `harness` (human_override needs a merge_override row in .migration/06_decisions.md naming the unit)
- Mapping version: `map-20260927c-custbill_lakeflow-v1`
- Tolerance version: `tol-20260927c-v1`
- Seed: `0` | Params: `{'ns': 'demo', 'batch_no': '85559852', 'admin_tenant_id': 'a0000000-0000-0000-0000-000000000001', 'fixture_tenant_id': '00000000-0000-0000-0000-000000000001'}`
- Tier 3 depth: `sampled`
- Generated: 2026-09-28T00:22:34.270564+00:00

## Routine parity: routine_parity_missing (no dependency analysis; commit .migration/units/custbill_lakeflow/dependencies.json, an empty `routines` list for a unit that writes nothing, or pass `--routine-dependencies`)
- Cost: `{"source_statements": 491, "source_rows_fetched": 304344, "target_statements": 338, "target_rows_fetched": 152108, "elapsed_s": 495.525}`
- **WARNING: UNVERIFIED structural_parity: structure unavailable: invoice_header: invoice_header: information_schema.table_privileges read failed (ServerOperationError)**
- **WARNING: UNVERIFIED structural_parity: structure unavailable: invoice_line: invoice_line: information_schema.table_privileges read failed (ServerOperationError)**
- **WARNING: UNVERIFIED structural_parity: structure unavailable: customer_master: customer_master: information_schema.table_privileges read failed (ServerOperationError)**
- **WARNING: UNVERIFIED structural_parity: structure unavailable: entity_attr_value: entity_attr_value: information_schema.table_privileges read failed (ServerOperationError)**

| Tier | Name | Checks | Result |
|---|---|---|---|
| 0 | structural_parity | 0 | PASS |
| 1 | counts_through_mapping | 4 | PASS |
| 2 | per_field_aggregates | 191 | PASS |
| 3 | keyed_diffs | 152108 | PASS |

## Tier 0 coverage
```json
{
  "dictionary_unavailable": [
    "invoice_header: invoice_header: information_schema.table_privileges read failed (ServerOperationError)",
    "invoice_line: invoice_line: information_schema.table_privileges read failed (ServerOperationError)",
    "customer_master: customer_master: information_schema.table_privileges read failed (ServerOperationError)",
    "entity_attr_value: entity_attr_value: information_schema.table_privileges read failed (ServerOperationError)"
  ],
  "structural_checks": {
    "constraints": "unsupported",
    "triggers": "unsupported",
    "indexes": "unsupported",
    "sequences_identity": "unsupported",
    "grants": "unsupported"
  },
  "structural_diff": {},
  "dictionary": {
    "source": "live",
    "target": "live"
  }
}
```

## Tier 1 coverage
```json
{
  "source_counts": {
    "OW_BILLING.INVOICE_HEADER": 18750,
    "OW_BILLING.INVOICE_LINE": 150000,
    "OW_BILLING.CUSTOMER_MASTER": 25000,
    "OW_BILLING.ENTITY_ATTR_VALUE": 8333
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoice_header.invoice_no",
    "invoice_header.invoice_dt",
    "invoice_header.due_dt",
    "invoice_line.invoice_no",
    "invoice_line.cust_no",
    "invoice_line.cust_name",
    "invoice_line.item_desc",
    "invoice_line.invoice_dt",
    "invoice_line.service_period",
    "invoice_line.posted_yn",
    "invoice_line.gl_acct_csv",
    "invoice_line.src_system",
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
    "entity_attr_value.entity_type",
    "entity_attr_value.attr_name",
    "entity_attr_value.attr_value",
    "entity_attr_value.attr_type",
    "entity_attr_value.created_dt"
  ]
}
```

## Tier 3 coverage
```json
{
  "invoice_header": {
    "mode": "stratified_sample",
    "sampling": "stratified",
    "strata": 32,
    "population": 18750,
    "sampled": 18750,
    "coverage": 1.0,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "invoice_line": {
    "mode": "stratified_sample",
    "sampling": "stratified",
    "strata": 32,
    "population": 150000,
    "sampled": 100025,
    "coverage": 0.666833,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "customer_master": {
    "mode": "stratified_sample",
    "sampling": "stratified",
    "strata": 32,
    "population": 25000,
    "sampled": 25000,
    "coverage": 1.0,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  },
  "entity_attr_value": {
    "mode": "stratified_sample",
    "sampling": "stratified",
    "strata": 32,
    "population": 8333,
    "sampled": 8333,
    "coverage": 1.0,
    "null_key_rows": {
      "source": 0,
      "target": 0
    },
    "duplicate_source_key_count": 0
  }
}
```
