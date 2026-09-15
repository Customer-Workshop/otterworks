# Recon report: unit `U2-customers`

- **Verdict: PASS**
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping version: `1`
- Tolerance version: `1`
- Seed: `714559852`
- Generated: 2026-09-15T05:33:22.610762+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 3 | PASS |
| 2 | per_field_aggregates | 29 | PASS |
| 3 | keyed_diffs | 33333 | PASS |
| 4 | app_level_parity | 26 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "CUSTOMER_MASTER": 25000,
    "CUSTOMER_MASTER_HIST": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "customers.custNo",
    "customers.tenantId",
    "customers.name",
    "customers.legalName",
    "customers.dbaName",
    "customers.segment",
    "customers.region",
    "customers.territory",
    "customers.channel",
    "customers.rateClass",
    "customers.balances.current",
    "customers.balances.pastDue",
    "customers.balances.ytdBilled",
    "customers.balances.ltdBilled",
    "customers.balances.ytdPaid",
    "customers.balances.creditLimit",
    "customers.contactNotes",
    "customers.legacy.sysKey",
    "customers.legacy.mainframeAcctNo",
    "customers.legacy.conversionBatchNo",
    "customers.legacy.custSeqNo",
    "customers.audit.createdBy",
    "customers.audit.updatedBy",
    "customers.audit.version",
    "customer_history.histId",
    "customer_history.op",
    "customer_history.customerId"
  ]
}
```

## Tier 3 coverage
```json
{
  "customers": {
    "mode": "full_diff",
    "population": 25000,
    "duplicate_source_key_count": 0
  },
  "embeds_graded": {
    "customers.attributes": 8333
  },
  "customer_history": {
    "mode": "full_diff",
    "population": 0,
    "duplicate_source_key_count": 0
  }
}
```
