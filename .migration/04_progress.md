# 04 — Progress ledger

One-screen table; doubles as the cutover readiness view and sign-off checklist.
Write targets MUST be registered here before any load; halt on collision.

DB prefix below: `ow` = `ow_tp_mongodb_032752`, `owq` = `ow_tp_mongodb_032752_quarantine`.

| Wave | Unit | Write target (db.collection) | Status | Parity | Quarantine rate | Unverified paths | Cost | PR |
|---|---|---|---|---|---|---|---|---|
| 0 | U0 shared-reference | ow.codes, ow.tenants, ow.plans, ow.fixture_meta | MERGED | GREEN (independent LIVE recon DRIFT-EXPLAINED, functionally PASS — wave report `recon/wave0-independent-20260901`:.migration/recon/wave_reports/wave0.md) | 0% (0 rejects, quarantine unused) | fixture_meta.INITIALIZED_AT declared-unexercised | M0 free tier, 105 docs | #1397 |
| 1 | U1 customers | ow.customers, ow.customer_master_hist | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 1 | U2 invoice-feed | ow.invoice_feed, owq.invoice_feed_orphan_lines | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 2 | U3 subscriptions | ow.subscriptions, ow.subscriptions_hist | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 2 | U4 rating | ow.usage_events, ow.rating_periods, ow.rating_results | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 2 | U7 audit-util | ow.billing_audit_log | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 3 | U5 invoicing | ow.invoices, ow.credit_notes | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 3 | U6 dunning | ow.notifications (+ embeds into ow.invoices, coordinated with U5) | PLANNED — AWAITING STOP B | — | — | — | — | — |

## Registered write targets

All targets above are registered; U0's four targets are registered and flipped to IN
PROGRESS (STOP B approved per 05_decisions.md). No collisions: each collection has exactly
one owning unit
(U6's dunning_attempts[] embed lands via the U5/U6 sequential batch that owns ow.invoices).
