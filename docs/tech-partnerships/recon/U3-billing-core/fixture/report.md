# Recon report: unit `U3-billing-core`

- **Verdict: PASS** (values redacted)
- Mode: `fixture` (fixture data: NOT a merge verdict, run live once before merging) | Target: `local` (local target: NOT a merge verdict)
- Merge eligible: no (fixture/continuous evidence never merges)
- Mapping version: `map-1` (sha256 `e6fda9603553`)
- Tolerance version: `1` (sha256 `03b3c6cc0bc6`)
- Collections: `billing_invoices`, `subscriptions`, `subscriptions_hist`, `usage_events`, `rating_periods`, `rating_results`, `credit_notes`, `dunning_attempts`, `notifications`, `billing_audit_log`
- Seed: `0`
- Generated: 2026-09-29T19:05:06.612352+00:00
- 41 fields: Tier 2 aggregates deferred to Tier 3 (rules change the value)
- 19 string fields: min/max/distinct deferred to Tier 3

| Tier | Name | Checks | Result |
|---|---|---|---|
| 1 | counts_through_mapping | 11 | PASS |
| 2 | per_field_aggregates | 28 | PASS |
| 3 | keyed_diffs | 896 | PASS |

## Tier 1 coverage
```json
{
  "source_counts": {
    "billing_invoices": 4,
    "subscriptions": 70,
    "subscriptions_hist": 0,
    "usage_events": 805,
    "rating_periods": 3,
    "rating_results": 3,
    "credit_notes": 5,
    "dunning_attempts": 1,
    "notifications": 1,
    "billing_audit_log": 0
  }
}
```

## Tier 2 coverage
```json
{
  "deferred_to_tier3": [
    "billing_invoices.tenant_id",
    "billing_invoices.period_id",
    "billing_invoices.issued_at",
    "billing_invoices.subtotal",
    "billing_invoices.tax",
    "billing_invoices.total",
    "subscriptions.tenant_id",
    "subscriptions.plan_id",
    "subscriptions.starts_on",
    "subscriptions.ends_on",
    "subscriptions.suspended_on",
    "subscriptions_hist.hist_dt",
    "subscriptions_hist.hist_op",
    "subscriptions_hist.id",
    "subscriptions_hist.tenant_id",
    "subscriptions_hist.plan_id",
    "subscriptions_hist.starts_on",
    "subscriptions_hist.ends_on",
    "subscriptions_hist.status_cd",
    "subscriptions_hist.suspended_on",
    "usage_events.tenant_id",
    "usage_events.occurred_at",
    "rating_periods.tenant_id",
    "rating_periods.period_start",
    "rating_periods.period_end",
    "rating_results.period_id",
    "rating_results.subscription_id",
    "rating_results.overage_amount",
    "rating_results.created_at",
    "credit_notes.tenant_id",
    "credit_notes.issued_on",
    "credit_notes.amount",
    "credit_notes.remaining_amount",
    "dunning_attempts.tenant_id",
    "dunning_attempts.invoice_id",
    "dunning_attempts.scheduled_for",
    "notifications.tenant_id",
    "notifications.sent_at",
    "billing_audit_log.logged_at",
    "billing_audit_log.module",
    "billing_audit_log.message"
  ],
  "string_aggregates_deferred_to_tier3": [
    {
      "field": "billing_invoices.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "billing_invoices.period_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions.plan_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions_hist.hist_dt",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions_hist.hist_op",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions_hist.id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions_hist.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "subscriptions_hist.plan_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "usage_events.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "rating_periods.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "rating_results.period_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "rating_results.subscription_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "credit_notes.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "dunning_attempts.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "dunning_attempts.invoice_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "notifications.tenant_id",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "billing_audit_log.module",
      "stats": [
        "min",
        "max",
        "distinct_count"
      ]
    },
    {
      "field": "billing_audit_log.message",
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
  "billing_invoices": {
    "mode": "full_diff",
    "population": 4,
    "duplicate_source_key_count": 0
  },
  "embeds_graded": {
    "billing_invoices.lines": 4
  },
  "subscriptions": {
    "mode": "full_diff",
    "population": 70,
    "duplicate_source_key_count": 0
  },
  "subscriptions_hist": {
    "mode": "full_diff",
    "population": 0,
    "duplicate_source_key_count": 0
  },
  "usage_events": {
    "mode": "full_diff",
    "population": 805,
    "duplicate_source_key_count": 0
  },
  "rating_periods": {
    "mode": "full_diff",
    "population": 3,
    "duplicate_source_key_count": 0
  },
  "rating_results": {
    "mode": "full_diff",
    "population": 3,
    "duplicate_source_key_count": 0
  },
  "credit_notes": {
    "mode": "full_diff",
    "population": 5,
    "duplicate_source_key_count": 0
  },
  "dunning_attempts": {
    "mode": "full_diff",
    "population": 1,
    "duplicate_source_key_count": 0
  },
  "notifications": {
    "mode": "full_diff",
    "population": 1,
    "duplicate_source_key_count": 0
  },
  "billing_audit_log": {
    "mode": "full_diff",
    "population": 0,
    "duplicate_source_key_count": 0
  }
}
```
