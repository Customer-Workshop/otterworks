# Recon report: unit `w1-b02`

- **Verdict: PASS** (values redacted)
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1.1.0`
- Tolerance version: `1.0.0`
- Seed: `20260926`
- Generated: 2026-09-26T18:21:43.392082+00:00
- 29 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 18 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 2 | PASS |
| 2 | per_field_aggregates | 5 | PASS |
| 3 | keyed_diffs | 19754 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "invoice_headers": 18750,
    "invoice_lines": 150000
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "invoice_headers.invoiceId",
    "invoice_headers.invoiceNo",
    "invoice_headers.custId",
    "invoice_headers.tenantId",
    "invoice_headers.invoiceDt",
    "invoice_headers.dueDt",
    "invoice_headers.statusCd",
    "invoice_headers.totalAmt",
    "invoice_headers.batchNo",
    "invoice_lines.lineId",
    "invoice_lines.invoiceNo",
    "invoice_lines.invoiceId",
    "invoice_lines.custId",
    "invoice_lines.custNo",
    "invoice_lines.custName",
    "invoice_lines.tenantId",
    "invoice_lines.lineNo",
    "invoice_lines.lineTypeCd",
    "invoice_lines.itemDesc",
    "invoice_lines.qty",
    "invoice_lines.unitPrice",
    "invoice_lines.amount",
    "invoice_lines.taxAmt",
    "invoice_lines.invoiceDt",
    "invoice_lines.servicePeriod",
    "invoice_lines.postedYn",
    "invoice_lines.glAcctCsv",
    "invoice_lines.batchNo",
    "invoice_lines.srcSystem"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "invoice_headers.invoiceId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_headers.invoiceNo",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_headers.custId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_headers.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_headers.invoiceDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_headers.dueDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.lineId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.invoiceNo",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.invoiceId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.custId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.custNo",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.custName",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.tenantId",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.itemDesc",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.invoiceDt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.servicePeriod",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.glAcctCsv",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "invoice_lines.srcSystem",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    }
  ],
  "fields_fully_deferred": 24
}
```

## Tier 3 coverage
```json
{
  "invoice_headers": {
    "mode": "full_diff",
    "population": 18750,
    "duplicate_source_key_count": 0
  },
  "invoice_lines": {
    "mode": "stratified_sample",
    "population": 150000,
    "sampled": 1004,
    "coverage": 0.006693,
    "duplicate_source_key_count": 0
  }
}
```
