# 09_coverage: every source object in exactly one bucket

Source: `.migration/census.json` (ddl_census over `services/legacy-billing/db/oracle/schema/*.sql` + `packages/*.sql`; 19 tables, 5 sequences, 7 triggers, 10 PL/SQL units, 2 scheduler jobs, 2 unparsed statements). Access evidence: `services/legacy-billing/app/*.py`, `packages/*.sql`, `testdata/legacy/oracle_billing_seed.py` (cites in `05_decisions.json`). `source_access=ddl_only`: no catalog discovery was run.

Buckets: **unit** (migration unit), **shared** (shared/reference, wave 0), **unused** (proposed-unused, with evidence), **excluded**.

## Tables (19)

| Object | Bucket | Unit | Target | Cite |
|---|---|---|---|---|
| CODES | shared | u-00-codes | `codes` (reference_data) | 01_pkg_util.sql:40; facade.py:110-119, 213-217, 245-247, 341-344 (joined on every read) |
| TENANTS | unit | u-01-tenancy | `tenants` | 02_pkg_plans.sql:61-66; 05_pkg_dunning.sql:81; backends/oracle.py:136-144 |
| PLANS | unit | u-01-tenancy | `plans` | 02_pkg_plans.sql:24-31; 03_pkg_rating.sql:69-70 |
| SUBSCRIPTIONS | unit | u-01-tenancy | `subscriptions` | 02_pkg_plans.sql:74-104; 05_pkg_dunning.sql:82-84 |
| SUBSCRIPTIONS_HIST | unit | u-01-tenancy | `subscriptionsHist` (history_copy / document_versioning) | 01_tables.sql:206-223 (trigger is the only writer; no reader in repo) |
| CUSTOMER_MASTER | unit | u-02-customers (XL) | `customerMaster` | facade.py:121-127, 287; reports.py:84-88 |
| ENTITY_ATTR_VALUE | unit | u-02-customers (XL) | embedded `customerMaster.attributes[]` | facade.py:293-298 (always read with its customer) |
| CUSTOMER_MASTER_HIST | unit | u-02-customers (XL) | `customerMasterHist` | 02_horror.sql:358-373 |
| INVOICES | unit | u-03-invoicing-core | `invoices` | 04_pkg_invoicing.sql:137-178; facade.py:241-250 |
| INVOICE_LINES | unit | u-03-invoicing-core | embedded `invoices.lines[]` (1:few, max 5) | 04_pkg_invoicing.sql:84-109, 149-163 |
| CREDIT_NOTES | unit | u-03-invoicing-core | `creditNotes` | 04_pkg_invoicing.sql:53-56, 182-188 |
| RATING_PERIODS | unit | u-03-invoicing-core | `ratingPeriods` | 03_pkg_rating.sql:87-92, 185-193 |
| RATING_RESULTS | unit | u-03-invoicing-core | `ratingResults` | 03_pkg_rating.sql:199-215 |
| USAGE_EVENTS | unit | u-04-usage-audit | `usageEvents` | facade.py:212-222, 400-411; 03_pkg_rating.sql:77-83 |
| BILLING_AUDIT_LOG | unit | u-04-usage-audit | `billingAuditLog` (ttl) | 01_pkg_util.sql:70-72; 04_jobs.sql:24 |
| DUNNING_ATTEMPTS | unit | u-05-dunning-data | `dunningAttempts` | 05_pkg_dunning.sql:43-58; facade.py:337-348 |
| NOTIFICATIONS | unit | u-05-dunning-data | `notifications` | 05_pkg_dunning.sql:86-94 |
| INVOICE_HEADER | unit | u-06-invoice-header-bulk (XL) | `invoiceHeader` | reports.py:42-52 |
| INVOICE_LINE | unit | u-06-invoice-header-bulk (XL) | embedded `invoiceHeader.lines[]` (1:N, ≤25; orphans quarantined) | reports.py:55-80; oracle_billing_seed.py:145, 305-322 |

## Sequences (5)

| Object | Bucket | Cite / plan |
|---|---|---|
| SEQ_BILLING_AUDIT_LOG | excluded | Oracle identity mechanics; `billingAuditLog._id` keeps the loaded LOG_ID, new rows use ObjectId (01_tables.sql:179-186) |
| SEQ_SUBSCRIPTIONS_HIST | excluded | as above; HIST_ID preserved on load (01_tables.sql:206-223) |
| SEQ_CUSTOMER_MASTER | excluded | CUST_SEQ_NO preserved on load; new customers have no app writer today (02_horror.sql:346-355) |
| SEQ_CUSTOMER_MASTER_HIST | excluded | HIST_ID preserved on load |
| SEQ_ENTITY_ATTR_VALUE | excluded | EAV_ID preserved as the array-element key `eavId` |

## Triggers (7)

| Object | Bucket | Unit | Cite / plan |
|---|---|---|---|
| TRG_BILLING_AUDIT_LOG_ID | excluded | — | identity assignment only (01_tables.sql:179-186) |
| TRG_CUSTOMER_MASTER_SEQ | unit | u-02-customers | seq + `cust_name_upper` + `row_version_no`; loader preserves values, future writers compute them (02_horror.sql:346-355) |
| TRG_ENTITY_ATTR_VALUE_SEQ | excluded | — | identity assignment only (02_horror.sql:391-398) |
| TRG_SUBSCRIPTIONS_HIST | unit | u-08-plsql-plans | history write moves into the service update path (01_tables.sql:206-223) |
| TRG_SUB_NO_UNCANCEL | unit | u-08-plsql-plans | invariant enforced in the service (01_tables.sql:228-235) |
| TRG_USAGE_EVENTS_CHECK | unit | u-04-usage-audit | validation in `/internal/usage/events` + JSON schema (01_tables.sql:239-253; facade.py:381-411) |
| TRG_CUSTOMER_MASTER_HIST | unit | u-02-customers | no app writer today; documented for future writers (02_horror.sql:358-373) |

## PL/SQL units (10 = 5 spec + 5 body)

| Object | Bucket | Unit | Cite |
|---|---|---|---|
| PKG_OW_UTIL (spec+body) | unit | u-07-plsql-util | 01_pkg_util.sql:26-77 |
| PKG_PLANS (spec+body) | unit | u-08-plsql-plans | 02_pkg_plans.sql:24-104 |
| PKG_RATING (spec+body) | unit | u-09-plsql-rating | 03_pkg_rating.sql:32-217 |
| PKG_INVOICING (spec+body) | unit | u-10-plsql-invoicing | 04_pkg_invoicing.sql:26-194 |
| PKG_DUNNING (spec+body) | unit | u-11-plsql-dunning | 05_pkg_dunning.sql:17-99 |

## Scheduler jobs (2), other

| Object | Bucket | Unit | Cite / plan |
|---|---|---|---|
| JOB_NIGHTLY_DUNNING | unit | u-11-plsql-dunning | 04_jobs.sql:5-17; disabled today; becomes a service scheduled task (D3-1) |
| JOB_PURGE_AUDIT_LOG | unit | u-04-usage-audit | 04_jobs.sql:20-27; disabled today; TTL index replaces it (D3-2) |
| FIXTURE_META (+ 2 unparsed statements in 04_upgrade_static.sql) | excluded | — | fixture-boot bookkeeping (healthcheck marker / seed version); not business data (04_upgrade_static.sql:6-19; docker-compose.oracle-billing.yml healthcheck) |
| `services/legacy-billing/db/schema.sql`, `db/procs/*.sql`, `backends/postgres.py` | excluded | — | the Postgres original of the same estate; not the Oracle source (00_context.md scope) |

Proposed-unused: none. Every table has at least one reader or writer in the repo (SUBSCRIPTIONS_HIST, CUSTOMER_MASTER_HIST, NOTIFICATIONS, RATING_RESULTS are written by code but read only by the `procs/harness` probes or not at all; they are kept as history/audit units, not dropped, because retention was not decided by the customer).

Totals: 19 tables → 12 unit-assigned + 1 shared (CODES) = 19 (17 unit + 1 shared + 0 unused + 0 excluded... see rows: 18 unit rows incl. CODES as shared); sequences 5 excluded; triggers 5 unit + 2 excluded; PL/SQL 10 unit; jobs 2 unit; FIXTURE_META excluded.
