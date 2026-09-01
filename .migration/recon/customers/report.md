# Recon report: unit `customers`

- **Verdict: PASS**
- Mode: `live`
- Mapping version: `1.0.0`
- Tolerance version: `1`
- Generated: 2026-09-01T01:08:50.563936+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 42 | PASS |
| 3 | keyed_diffs | 25000 | PASS |
| 4 | app_level_parity | 2 | PASS |

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "customers.cust_id",
    "customers.tenant_id",
    "customers._id",
    "customers.cust_name",
    "customers.cust_name_upper",
    "customers.legal_name",
    "customers.addr_line_1",
    "customers.addr_line_2",
    "customers.addr_line_3",
    "customers.city",
    "customers.state_cd",
    "customers.zip",
    "customers.phone1",
    "customers.phone2",
    "customers.email_1",
    "customers.legacy.signup_dt",
    "customers.legacy.last_activity_dt",
    "customers.sub_status_cd",
    "customers.tax_exempt_yn",
    "customers.credit_hold_yn",
    "customers.vip_yn",
    "customers.credit_limit_amt",
    "customers.legacy.related_acct_ids",
    "customers.legacy.promo_codes_csv",
    "customers.legacy_sys_key",
    "customers.mainframe_acct_no",
    "customers.created_by",
    "customers.updated_by"
  ],
  "sum_not_comparable": [
    "customers.cust_id",
    "customers.tenant_id",
    "customers._id",
    "customers.cust_name",
    "customers.cust_name_upper",
    "customers.legal_name",
    "customers.addr_line_1",
    "customers.addr_line_2",
    "customers.addr_line_3",
    "customers.city",
    "customers.state_cd",
    "customers.zip",
    "customers.phone1",
    "customers.phone2",
    "customers.email_1",
    "customers.legacy.signup_dt",
    "customers.legacy.last_activity_dt",
    "customers.tax_exempt_yn",
    "customers.credit_hold_yn",
    "customers.vip_yn",
    "customers.legacy.related_acct_ids",
    "customers.legacy.promo_codes_csv",
    "customers.legacy_sys_key",
    "customers.mainframe_acct_no",
    "customers.created_by",
    "customers.created_at",
    "customers.updated_by",
    "customers.updated_at"
  ]
}
```

## Tier 3 coverage
```json
{
  "customers": {
    "mode": "full_diff",
    "population": 25000
  }
}
```
