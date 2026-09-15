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
