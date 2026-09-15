# Recon report: unit `U1-reference`

- **Verdict: PASS**
- Mode: `live`
- Merge eligible: yes (fixture/continuous evidence never merges)
- Mapping version: `1`
- Tolerance version: `1`
- Seed: `714559852`
- Generated: 2026-09-15T05:05:32.043856+00:00

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 5 | PASS |
| 2 | per_field_aggregates | 15 | PASS |
| 3 | keyed_diffs | 173 | PASS |
| 4 | app_level_parity | 6 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "PLANS": 3,
    "CODES": 32,
    "TENANTS": 69,
    "SUBSCRIPTIONS_HIST": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "plans.code",
    "plans.monthlyFee",
    "plans.includedUnits",
    "plans.overageRate",
    "codes.codeType",
    "codes.codeVal",
    "codes.codeDesc",
    "tenants.name",
    "subscription_history.op",
    "subscription_history.subscriptionId",
    "subscription_history.tenantId",
    "subscription_history.planId",
    "subscription_history.startsOn",
    "subscription_history.endsOn",
    "subscription_history.suspendedOn"
  ]
}
```

## Tier 3 coverage
```json
{
  "plans": {
    "mode": "full_diff",
    "population": 3,
    "duplicate_source_key_count": 0
  },
  "codes": {
    "mode": "full_diff",
    "population": 32,
    "duplicate_source_key_count": 0
  },
  "tenants": {
    "mode": "full_diff",
    "population": 69,
    "duplicate_source_key_count": 0
  },
  "embeds_graded": {
    "tenants.subscriptions": 69
  },
  "subscription_history": {
    "mode": "full_diff",
    "population": 0,
    "duplicate_source_key_count": 0
  }
}
```
