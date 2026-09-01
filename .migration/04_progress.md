# 04 — Progress ledger

One-screen table; doubles as the cutover readiness view and sign-off checklist.
Write targets MUST be registered here before any load; halt on collision.

DB prefix below: `ow` = `ow_tp_mongodb_032752`, `owq` = `ow_tp_mongodb_032752_quarantine`.

| Wave | Unit | Write target (db.collection) | Status | Parity | Quarantine rate | Unverified paths | Cost | PR |
|---|---|---|---|---|---|---|---|---|
| 0 | U0 shared-reference | ow.codes, ow.tenants, ow.plans, ow.fixture_meta | MERGED | GREEN (independent LIVE recon DRIFT-EXPLAINED, functionally PASS — wave report `recon/wave0-independent-20260901`:.migration/recon/wave_reports/wave0.md) | 0% (0 rejects, quarantine unused) | fixture_meta.INITIALIZED_AT declared-unexercised | M0 free tier, 105 docs | #1397 |
| 1 | U1 customers | ow.customers, ow.customer_master_hist | MERGED | GREEN | 0% (quarantine unused, 0 orphans) | `customer_master_hist` empty at source; trigger-replacement history write path is unit-tested only; deployed HTTP reader path with `OW_BILLING_MONGO_URI` unexercised | M0 free tier, 25,000 docs | #1406 |
| 1 | U2 invoice-feed | ow.invoice_feed, owq.invoice_feed_orphan_lines | MERGED | GREEN | 0.0247% (37/150000 quarantined to owq) | UNKNOWN status/line-type branches; all-NULL SUM semantics; fixture-only run; reconciliation remains Oracle-backed via U1 | M0 free tier, 18750 roots + 149963 embedded lines + 37 quarantined | #1398 |
| 2 | U3 subscriptions | ow.subscriptions, ow.subscriptions_hist | MERGED | GREEN (independent LIVE recon PASS 86/86, mapping 1.2 / tolerances 1.0 — wave report `recon/wave2-independent-20260901`:.migration/recon/wave_reports/wave2.md) | 0% (quarantine unused, 0 rejects) | `subscriptions_hist` empty at source (0 rows); app-side trigger-replacement history/change-plan write paths are unit-tested only; ends_on/suspended_on all-NULL in NS=demo — Tier-2 native aggregates deferred to Tier-3 keyed diff per v1.2 amendment | M0 free tier, 69 docs | #1409 |
| 2 | U4 rating | ow.usage_events, ow.rating_periods, ow.rating_results | MERGED | GREEN (independent LIVE recon PASS 838/838, mapping 1.1 / tolerances 1.0 — wave report `recon/wave2-independent-20260901`:.migration/recon/wave_reports/wave2.md) | 0% (0 rejects, quarantine unused) | suppressed audit-log write (U7 owns `billing_audit_log`); Mongo-backed `subscriptions` read pending U3 (parity served from read-only Oracle extract); `UNKNOWN` usage-kind default unexercised; fixture-only run | M0 free tier, 820 docs | #1408 |
| 2 | U7 audit-util | ow.billing_audit_log | MERGED | GREEN (independent LIVE recon PASS 4/4 over genuinely empty source, mapping 1.1 / tolerances 1.0 — wave report `recon/wave2-independent-20260901`:.migration/recon/wave_reports/wave2.md) | 0% (quarantine unused, 0 rejects) | empty source population, so the mapped transforms and the v1.1 module/message tier-3 deferral grade nothing; `f_str2dt` three-digit years; `log_msg` has no migrated caller until U3-U6; TTL expiry timing observed, not contracted; fixture-only run | M0 free tier, 0 docs + TTL index | #1407 |
| 3 | U5 invoicing | ow.invoices, ow.credit_notes | MERGED | GREEN (independent LIVE recon PASS — gate Tier1 3/3, Tier2 11/11, Tier3 full diff, 0 findings; replay 144/144 preview + 2/2 transcripts + 4/4 invoice_lines; mapping 1.2 / tolerances 1.0 — wave report `recon/wave3a-independent-20260901`:.migration/recon/wave_reports/wave3a.md) | 0% (unused) | fixture-only run; `invoices.dunning_attempts[]` excluded/deferred to U6; suppressed audit-log write; no-plan/missing-plan preview path unit-tested but not transcript-exercised; transaction rollback and malformed-source branches unexercised | M0 free tier, 3 roots + 2 embedded lines + 5 credit notes | #1411 |
| 3 | U6 dunning | ow.notifications, ow.invoices.dunning_attempts[] (coordinated additive embed, U5/U6 sequential batch) | IN PROGRESS — fixture recon PASS, RECON_GREEN pending the independent live gate | fixture recon PASS (Tier1 4/4, Tier2 10/10, Tier3 7/7 with `invoices.dunning_attempts` graded, no exclusion; replay 5/5 DUNNING transcripts; mapping 1.2 / tolerances 1.0 — `.migration/recon/U6/gate/result.json`) | 0% (0 rejects, quarantine unused, 0 orphan attempts) | fixture-only run; real PL/SQL not invoked (transcript replay only); disabled nightly scheduler replaced by a manual entrypoint, no schedule activated; `WHEN OTHERS THEN NULL` swallow and Atlas transaction rollback not induced (mongomock shim only); runtime writes to U0/U3-owned `tenants`/`subscriptions` exercised only in replay; `UNKNOWN` code branches unexercised; suppressed audit-log write (U7 owns `billing_audit_log`) | M0 free tier, 1 notification + 1 embedded attempt across 3 invoices | — |

## Registered write targets

All targets above are registered; U0's four targets are registered and flipped to IN
PROGRESS (STOP B approved per 05_decisions.md), and U1's `ow.customers` plus
`ow.customer_master_hist` targets are registered for its wave. No collisions: each
collection has exactly one owning unit
(U6's dunning_attempts[] embed lands via the U5/U6 sequential batch that owns ow.invoices).
U6's `ow.notifications` is registered for wave 3 with no collision. U6's coordinated
write into the U5-owned `ow.invoices` documents is registered here: it only `$set`s the
`dunning_attempts[]` array on existing invoice documents, drops nothing, and touches no
other root or embedded field. That co-write is pre-authorized by the wave plan as the
sequential U5→U6 batch, so it is not a collision halt. `PKG_DUNNING`'s suspension path
also writes `ow.tenants` (U0) and `ow.subscriptions` (U3) at runtime — that is migrated
application behaviour, not a U6 load target; it is exercised only by transcript replay,
which restores the baseline with the owning units' idempotent loaders.
U3's `ow.subscriptions` and `ow.subscriptions_hist` are registered for wave 2. No collisions: each has exactly one owning unit.

Wave 1 independent recon report branch: `recon/wave1-independent-20260901`.

Wave 2 independent recon report branch: `recon/wave2-independent-20260901` (commit a550b49d, `.migration/recon/wave_reports/wave2.md`).

Wave 3a independent recon report branch: `recon/wave3a-independent-20260901` (commit dbf0a487, `.migration/recon/wave_reports/wave3a.md`).
