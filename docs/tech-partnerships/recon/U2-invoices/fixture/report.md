# Recon report: unit `U2-invoices`

- **Verdict: PASS** (values redacted)
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging) | Target: `local` (local target: NOT a merge verdict)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping version: `map-1` (sha256 `e6fda9603553`)
- Tolerance version: `1` (sha256 `03b3c6cc0bc6`)
- Collections: `invoices`, `quarantine_invoice_line`
- Seed: `0`
- Generated: 2026-09-29T19:06:10.082259+00:00
- **WARNING: embed invoices.lines: scoped by a where-predicate; extra target elements not checked**
- 27 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 17 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 5 | PASS |
| 3 | keyed_diffs | 168750 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "invoices": 18750,
    "quarantine_invoice_line": 37
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoices.invoice_no",
    "invoices.cust_id",
    "invoices.tenant_id",
    "invoices.invoice_dt",
    "invoices.due_dt",
    "invoices.status_cd",
    "invoices.total_amt",
    "invoices.batch_no",
    "quarantine_invoice_line.invoice_no",
    "quarantine_invoice_line.invoice_id",
    "quarantine_invoice_line.cust_id",
    "quarantine_invoice_line.cust_no",
    "quarantine_invoice_line.cust_name",
    "quarantine_invoice_line.tenant_id",
    "quarantine_invoice_line.line_no",
    "quarantine_invoice_line.line_type_cd",
    "quarantine_invoice_line.item_desc",
    "quarantine_invoice_line.qty",
    "quarantine_invoice_line.unit_price",
    "quarantine_invoice_line.amount",
    "quarantine_invoice_line.tax_amt",
    "quarantine_invoice_line.invoice_dt",
    "quarantine_invoice_line.service_period",
    "quarantine_invoice_line.posted_yn",
    "quarantine_invoice_line.gl_acct_csv",
    "quarantine_invoice_line.batch_no",
    "quarantine_invoice_line.src_system"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "invoices.invoice_no",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoices.cust_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoices.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoices.invoice_dt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoices.due_dt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.invoice_no",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.invoice_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.cust_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.cust_no",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.cust_name",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.item_desc",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.invoice_dt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.service_period",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.posted_yn",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.gl_acct_csv",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "quarantine_invoice_line.src_system",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    }
  ],
  "fields_fully_deferred": 22
}
```

## Tier 3 coverage
```json
{
  "invoices": {
    "mode": "full_diff",
    "population": 18750,
    "duplicate_source_key_count": 0
  },
  "embed_extras_unchecked": [
    "invoices.lines"
  ],
  "embeds_graded": {
    "invoices.lines": 149963
  },
  "quarantine_invoice_line": {
    "mode": "full_diff",
    "population": 37,
    "duplicate_source_key_count": 0
  }
}
```
