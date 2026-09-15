# 06_decisions — human decisions, dated

Only decisions with a human reply behind them, or a soft-stop default that was accepted.
A decision recorded here is the only thing that can move a tolerance, a scope line, or a
dependency posture.

---

## D-001 — One-time Oracle DDL to enable CDC on the invoicing core

**Date:** 2026-09-15 · **Decided by:** engagement owner, in session · **Status:** applied

**Question.** The recon and CDC design assumed Oracle stays read-only. Ten of the tables
pipeline 1 depends on — including `CUSTOMER_MASTER` — had no supplemental logging, so CDC
could not cover them without `ALTER TABLE ... ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS` on
the source.

**Recommendation given.** Run CDC as a later track scoped to the ten tables already logged,
so no source DDL is needed.

**Decision.** Overridden. Reply: *"wire CDC into pipeline 1 from start and approved, touch
oracle and enabe CDC"*. CDC is in pipeline 1 from the start and the supplemental-log DDL was
authorized explicitly.

**What was done.** `ALTER TABLE OW_BILLING.<t> ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS` on
`CODES`, `CUSTOMER_MASTER`, `CUSTOMER_MASTER_HIST`, `ENTITY_ATTR_VALUE`, `INVOICE_HEADER`,
`INVOICE_LINE`, `PLANS`, `SUBSCRIPTIONS_HIST`, `USAGE_EVENTS` — nine tables; the tenth
candidate, `FIXTURE_META`, is fixture bookkeeping and was left alone. All nine returned OK;
19 of the 20 `OW_BILLING` tables now carry a log group. Run once under the admin secret
`ow-tp/oracle/admin`, audit trail at `/home/ubuntu/oracle_ddl_audit.txt` (no secret values).
Because supplemental logging raises redo volume on a t3.large with archive logs on the root
volume, an hourly RMAN housekeeping job (`/usr/local/bin/ow-archivelog-housekeeping.sh`,
keep 2 days) was installed on the instance at the same time.

**Standing constraint after this decision.** That DDL and that housekeeping job are the only
writes this engagement makes to Oracle, ever. Every other source access is read-only under
`ow-tp/oracle/ow_billing_ro`. This is a named exception to the factory's read-only-source
guardrail, not a relaxation of it: no further source write may be made on the strength of
this entry. A child that finds itself wanting one raises a D10 instead.

---

## D-002 — Pipeline 1 keeps a non-CDC correctness path

**Date:** 2026-09-15 · **Decided by:** owner accepted the flagged fallback · **Status:** standing

Debezium's LogMiner connector against Oracle AI Database 26ai Free is outside the commonly
tested matrix. If the CDC leg does not come up clean, pipeline 1's correctness path stays on
chunked JDBC backfill plus watermarked incremental reads so the pipeline can still reconcile
and reach STOP E, and the CDC leg is fixed alongside rather than blocking the run.

---

## D-003 — Reconciliation mode and tolerances (v1)

**Date:** 2026-09-15 · **Decided by:** engagement owner, in session · **Status:** frozen

Aggregate plus row-level fingerprinting. Money and row counts exact. 1e-9 relative on other
floats. Dates canonicalized to ISO before comparison, unparseable values kept as a declared
anomaly set. Known dirty data (orphan invoice lines, malformed CSV lists) compared as sets,
so the migration reproduces the estate rather than cleaning it. Full contract in
`03_recon_tolerances.md`; amendments need a new dated version and a re-verification scope.

---

## D-004 — Process contract

**Date:** 2026-09-15 · **Decided by:** engagement owner, in session · **Status:** standing

Pipelines run strictly in order, N+1 starting only when N is parked at STOP E. Fan-out is a
pilot wave of 3 then 5. Stops are decided in the web session and mirrored to Slack
`#ow-migrations` for visibility. Data-load posture is materialize everything. The cutover
principal is held by the engagement owner; STOP E is never default-accepted and the parent
never answers it.

---

## D-005 — Migration identity is the service principal, not the PAT

**Date:** 2026-09-15 · **Decided by:** parent, pending owner confirmation (D10-04) · **Status:** provisional

The intake named `DATABRICKS_DEMO_HOST`/`DATABRICKS_DEMO_TOKEN`. That PAT resolves to a human
user, which factory-doctor grades as a blocking row because unattended children would act as
a person. Same workspace and same verified capability surface is available through the OAuth
M2M service principal `dhrov_spa` (`DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET`), so the
run proceeds on the SP. Raised to the owner the same hour; reversible on reply.

---

## D-006 — Lakehouse Federation is required after all

**Date:** 2026-09-15 · **Decided by:** open — recommended to owner · **Status:** OPEN (D10-01)

The intake declined federation to avoid opening the security group. The recon harness then
turned out to refuse the Oracle source adapter outright (untested, raises before connecting),
and its documented remedy is to reconcile Oracle through Lakehouse Federation as
`--family databricks`. Recommendation: open 1521 on `sg-0eaf11f4434260e1e` to the Databricks
serverless NAT range for us-east-1 and nothing else. Until this is answered, recon can only
run in DEGRADED snapshot mode, which is not sufficient evidence for STOP E.

---

## D-007 — STOP A: setup accepted (soft-mode default)

**Date:** 2026-09-15 · **Decided by:** default-accepted (soft stop_mode), presented to owner · **Status:** accepted

factory-doctor reports `ready=True` (16 ok, 2 skipped, 0 fail) against workspace
`dbc-8bc9474f-40ae`, catalog allowlist `['ow_tp']`, guard mode `block`, hook probe blocked
live, recon harness selftest PASS. The two skipped rows (`delete_evidence`,
`source_principal_read_only`) are not applicable until unit mappings exist; both are
re-checked before wave 1. The identity row passes when the expectation is written as the
service principal's object id `2e90bc1d-e9a1-4703-8c48-ad28ebb1864d` — the display name
`dhrov_spa` is not what the API returns. D10-04 (owner confirmation of the SP) stays open
independently of this row.

---

## D-008 — Who consumes the finance close

**Date:** 2026-09-15 · **Decided by:** open — asked at STOP B · **Status:** OPEN (D4-01)

`finance_excel_report.pl` mails its CSV-renamed-to-`.xls` through a sendmail pipe that has
been dead for years, so the estate does not reveal who reads the month-end close today or
what artifact they accept. Pipeline 2 cannot state acceptance criteria without it. Not
blocking now; blocking at pipeline 2's STOP C.

---

## D-009 — The util package's audit write is declared, not dropped

**Date:** 2026-09-15 · **Decided by:** owner (relayed by the parent) · **Status:** accepted

`pkg_ow_util.log_msg` inserts into the audit table, and every other package calls it, so any
unit converting a package inherits a write to `billing.billing_audit_log` that its own batch
does not declare. It halted wave 2 (w2-a) and then wave 3 twice (`p1-pkg-rating`,
`p1-pkg-invoicing`); a third batch (`p1-pkg-dunning`) converted without the logging to stay
inside its declared scope, which is the wrong resolution — the logging is legacy behaviour we
preserve.

Decision: declare `billing.billing_audit_log` as a runtime write on every batch whose unit
converts a package (w3-a, w3-b, w3-d here), restore the dropped `log_msg` calls in
`p1-pkg-dunning`, and re-run the collision check. `sp_issue_invoice` also calls
`pkg_rating.sp_finalize_rating`, so `p1-pkg-invoicing` genuinely writes
`billing.rating_periods` and `billing.rating_results`; those are declared too rather than
re-cutting the unit boundary this late.

Consequence on sequencing: a runtime write is only safe once the owning unit merged in an
earlier wave, because same-wave batches share one Lakebase branch and would otherwise race.
Wave 3 owns the two rating tables, so `p1-pkg-invoicing` moves from batch w3-b to a new
wave-4 batch `w4-b` (wave 4 width 2). The unit boundary is unchanged; only its wave is.
Manifests revalidate at 27 units / 47 write targets / 11 runtime writes / no collisions.

Carried to STOP E as one named finding: the util package writes the audit log from inside
every other package, so a manifest that does not model it produces an undeclared write in
every package unit.

---

## D-010 — Oracle TIMESTAMP maps to Postgres `timestamp`, not `timestamptz`

**Date:** 2026-09-15 · **Decided by:** parent (delegated non-blocking call) · **Status:** accepted

Six frozen mapping specs typed an Oracle `TIMESTAMP` column as Postgres `timestamptz`
(`p1-invoices`, `p1-rating-results`, `p1-notifications`, `p1-pkg-invoicing`, `p1-pkg-rating`,
`p1-pkg-dunning`). Plain Oracle `TIMESTAMP` carries no zone, so a zone-aware target column
reads back as a different value and fails tier 3 on every row. All three wave-3 batches found
it independently.

This is a spec defect corrected after the freeze, not a tolerance change: tolerances stay
frozen, money stays exact, and canonicalization is untouched. The six specs now read
`timestamp(6)` and `gen_mapping_specs.py` emits `timestamp(p)` for the `TIMESTAMP` base type,
so the defect cannot be regenerated. STOP E records that six columns were re-typed after the
specs were frozen, and why.

---

## D-011 — `usage_events` lands on both tracks; `pkg_rating` moves to wave 4 behind it

**Date:** 2026-09-15 · **Decided by:** user (explicit reply) · **Status:** accepted

`pkg_rating` reads `usage_events` row-at-a-time in `compute_rating` and `fn_usage_summary`,
but `usage_events` was placed on the analytical track in wave 1 (`ow_tp.silver.usage_events`)
and no `billing.usage_events` exists in Lakebase. Wave 3's `p1-pkg-rating` reported BLOCKED
rather than materialising an undeclared copy inside a package unit, and the independent
verifier agreed that was the correct refusal. The same gap blocks `p1-pkg-invoicing`, because
`sp_issue_invoice` calls `sp_finalize_rating`.

Decision: add `p1-usage-events-oltp` (U-28) as a wave-4 unit on the operational track, with
`billing.usage_events` as its declared write target. The Delta copy stays and remains the
analytical one. The two units share one source table and have disjoint write targets, and
each reconciles against Oracle — never one target against the other.

Sequencing, serialized inside wave 4: `w4-c` (`p1-usage-events-oltp`) → `w4-d`
(`p1-pkg-rating`, retried) → `w4-b` (`p1-pkg-invoicing`). `w4-a` (the nightly dunning job) is
independent of the rating chain and already running. `p1-pkg-rating` is re-placed from w3-a
to w4-d for the reason D-009 moved `p1-pkg-invoicing`: a runtime write to the rating tables
is only safe once the wave that owns those tables has delivered them. Wave 3's manifest keeps
the two rating data units, and its result artifact still records that `p1-pkg-rating` ran
there and was blocked.

Rejected alternative: leave rating on the analytical track. Invoicing would then stop being a
Lakebase transaction, which is the operational contract this migration exists to preserve.

Not a tolerance change: tolerances stay frozen and money stays exact. Manifests revalidate at
28 units / 48 write targets / 14 runtime writes / no collisions.

STOP E records that one source table is materialised on both tracks, that the operational
copy is loaded by the migration rather than by the application, and that keeping the two
copies in step after cutover needs a named owner.
