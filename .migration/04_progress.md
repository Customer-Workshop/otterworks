# 04 — Progress ledger

One-screen table; doubles as the cutover readiness view and sign-off checklist.
Write targets MUST be registered here before any load; halt on collision.

DB prefix below: `ow` = `ow_tp_mongodb_032752`, `owq` = `ow_tp_mongodb_032752_quarantine`.

| Wave | Unit | Write target (db.collection) | Status | Parity | Quarantine rate | Unverified paths | Cost | PR |
|---|---|---|---|---|---|---|---|---|
| 0 | U0 shared-reference | ow.codes, ow.tenants, ow.plans, ow.fixture_meta | MERGED | GREEN (independent LIVE recon DRIFT-EXPLAINED, functionally PASS — wave report `recon/wave0-independent-20260901`:.migration/recon/wave_reports/wave0.md) | 0% (0 rejects, quarantine unused) | fixture_meta.INITIALIZED_AT declared-unexercised | M0 free tier, 105 docs | #1397 |
| 1 | U1 customers | ow.customers, ow.customer_master_hist | MERGED | GREEN | 0% (quarantine unused, 0 orphans) | `customer_master_hist` empty at source; trigger-replacement history write path is unit-tested only; deployed HTTP reader path with `OW_BILLING_MONGO_URI` unexercised | M0 free tier, 25,000 docs | #1406 |
| 1 | U2 invoice-feed | ow.invoice_feed, owq.invoice_feed_orphan_lines | MERGED | GREEN | 0.0247% (37/150000 quarantined to owq) | UNKNOWN status/line-type branches; all-NULL SUM semantics; fixture-only run; reconciliation remains Oracle-backed via U1 | M0 free tier, 18750 roots + 149963 embedded lines + 37 quarantined | #1398 |
| 2 | U3 subscriptions | ow.subscriptions, ow.subscriptions_hist | RECON_GREEN (fixture; PR open, awaiting wave gate) | GREEN (fixture recon PASS, mapping 1.2 / tolerances 1.0) | 0% (quarantine unused, 0 rejects) | `subscriptions_hist` empty at source (0 rows); app-side trigger-replacement history/change-plan write paths are unit-tested only; ends_on/suspended_on all-NULL in NS=demo — Tier-2 native aggregates deferred to Tier-3 keyed diff per v1.2 amendment | M0 free tier, 69 docs | — |
| 2 | U4 rating | ow.usage_events, ow.rating_periods, ow.rating_results | RECON_GREEN (fixture self-check `.migration/recon/U4/gate/result.json`; wave gate owns LIVE) | GREEN (tiers 3/15/820 PASS; 8/8 recorded rating transcripts replay PASS) | 0% (0 rejects, quarantine unused) | suppressed audit-log write (U7 owns `billing_audit_log`); Mongo-backed `subscriptions` read pending U3 (parity served from read-only Oracle extract); `UNKNOWN` usage-kind default unexercised; fixture-only run | M0 free tier, 820 docs | #1408 |
| 2 | U7 audit-util | ow.billing_audit_log | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 3 | U5 invoicing | ow.invoices, ow.credit_notes | PLANNED — AWAITING STOP B | — | — | — | — | — |
| 3 | U6 dunning | ow.notifications (+ embeds into ow.invoices, coordinated with U5) | PLANNED — AWAITING STOP B | — | — | — | — | — |

## Registered write targets

All targets above are registered; U0's four targets are registered and flipped to IN
PROGRESS (STOP B approved per 05_decisions.md), and U1's `ow.customers` plus
`ow.customer_master_hist` targets are registered for its wave. No collisions: each
collection has exactly one owning unit
(U6's dunning_attempts[] embed lands via the U5/U6 sequential batch that owns ow.invoices).
U3's `ow.subscriptions` and `ow.subscriptions_hist` are registered for wave 2. No collisions: each has exactly one owning unit.

Wave 1 independent recon report branch: `recon/wave1-independent-20260901`.
