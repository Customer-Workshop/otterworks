# OW_BILLING target state

This is the setup contract for child migration sessions. Every field below is explicitly
`FACT` or `PROPOSED`. A `FACT` cites the source of record with a `path:line` reference;
the merged reference implementation on `origin/tech-partnerships-solutions` outranks
planning prose where both exist.

## CORE

| Field | Status and value |
|---|---|
| Estate and scope | **FACT** — `OW_BILLING` is the only estate in this run; `COMMISSION_DW` is out of scope (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:153-154`). |
| Unity Catalog catalog | **FACT** — `ow_tp` (`docs/tech-partnerships/contracts/README.md:15-18`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/variables.tf:12-19`). |
| Schemas | **FACT** — `bronze`, `silver`, and `gold` (`docs/tech-partnerships/contracts/README.md:15-18`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/main.tf:37-52`). |
| Managed landing volume | **FACT** — `/Volumes/ow_tp/bronze/landing` (`docs/tech-partnerships/contracts/README.md:15-18`; `docs/tech-partnerships/databricks-fixture-spike.md:23-30`). |
| Secret scope | **FACT** — `ow_tp` (`docs/tech-partnerships/contracts/README.md:15-18`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/main.tf:65-76`). |
| Notebook root | **FACT** — `/Shared/ow_tp` (`docs/tech-partnerships/contracts/README.md:15-18`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/main.tf:78-83`). |
| Workspace naming | **FACT** — every created object carries `ow_tp`; jobs are named `ow_tp_<unit>` (`docs/tech-partnerships/contracts/README.md:23-26`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/README.md:10-20`). |
| Compute | **FACT** — create no compute. Use the existing serverless SQL warehouse as a data source and serverless notebook/job compute; no hourly-floor resource (`docs/tech-partnerships/contracts/README.md:23-26`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/README.md:17-20`). |
| Unprefixed objects | **FACT** — never read, write, or delete an unprefixed object (`docs/tech-partnerships/contracts/README.md:23-26`). |
| Terraform ownership | **FACT** — a child contributes only `infrastructure/terraform-databricks/jobs_<unit>.tf`; it never edits the shared stack or runs `terraform apply`/`destroy` (`docs/tech-partnerships/contracts/README.md:19-22`). |
| Namespace parameter | **FACT** — every job takes `ns`; volume paths use `<ns>/<unit>/...` and table rows carry `ns` (`docs/tech-partnerships/contracts/README.md:27-29`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/README.md:33-35`). |
| Secrets | **FACT** — use `dbutils.secrets`; do not inline values (`origin/tech-partnerships-solutions:infrastructure/terraform-databricks/README.md:47-51`). |
| Repository helper | **FACT** — SQL, uploads, notebook deploys, and job runs use `scripts/tp_databricks/dbx.py`; it resolves `DATABRICKS_HOST`/`TOKEN` or the `DATABRICKS_DEMO_*` fallbacks and does not create compute (`origin/tech-partnerships-solutions:scripts/tp_databricks/dbx.py:2-19`). |
| Recon artifact | **FACT** — use `*.recon.json`, with `kind: recon-report`, validated against `docs/tech-partnerships/contracts/schema/recon-report.schema.json` (`docs/tech-partnerships/contracts/README.md:8-11`; `docs/tech-partnerships/contracts/schema/recon-report.schema.json:1-35`). |
| Smoke gate | **FACT** — every PR passes `make tp-smoke` (`docs/tech-partnerships/contracts/README.md:35-37`). |
| PR and branch topology | **FACT** — one PR per migration unit; children use `migrate/ow_billing/<wave>-<unit>` from the run branch (`docs/tech-partnerships/contracts/README.md:38-43`; `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:235-236`). |
| Branch contents | **FACT** — branches contain code only: no data, state files, or secrets (`docs/tech-partnerships/contracts/README.md:27-29`). |

## SQL profile (dominant workload surface)

| Field | Status and value |
|---|---|
| Source mapping | **FACT** — PL/SQL packages map to Spark SQL notebooks; `PKG_RATING` exposes rating and finalization entrypoints and `PKG_INVOICING` calls rating (`services/legacy-billing/db/oracle/packages/03_pkg_rating.sql:1-27`; `services/legacy-billing/db/oracle/packages/04_pkg_invoicing.sql:1-20,113-135`). |
| Python boundary | **FACT** — use PySpark only where set-based SQL cannot express the logic (`docs/tech-partnerships/runbook-databricks.md:100-115`). |
| Dialect policy | **FACT** — no Oracle dialect skill exists; interim policy is generic ANSI translation and every Oracle-specific semantic is decided centrally before fan-out (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:95-105`). |
| Numeric money type | **FACT** — money is `DECIMAL(14,2)` end to end; any `DOUBLE` in a money lineage rejects the PR (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:155-156`; `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:247-248`). |
| Materialization | **PROPOSED** — materialize business results as gold Delta tables with liquid clustering; do not use views or materialized views. |
| Source-side views | **FACT** — N/A: the intake census found zero views (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:27-49`). |
| Sequences | **PROPOSED** — replace Oracle sequences and trigger-generated keys with a centrally pinned identity/surrogate-key policy; do not port each sequence one-for-one. |
| Semantic dictionary | **PROPOSED** — resolve Oracle semantics once in the dictionary before child fan-out; child PRs may consume but not redefine those decisions. |
| Opening hazard agenda | **FACT** — address string dates, `NVL`/`DECODE`, `TO_DATE`, `ROWNUM`, `WHEN OTHERS THEN NULL`, EAV, 155/158-column tables, and unprecisioned `NUMBER` first (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:107-118`). |
| Date policy | **FACT** — unparseable `VARCHAR2(9)` dates quarantine the row, continue the load, and count the quarantine in recon (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:155-156`). |
| SQL drift rules | **PROPOSED** — reject a PR for `DOUBLE` money, per-child Oracle semantic reinterpretation, untyped `NUMBER`, an MV/view in place of the declared gold Delta table, an unhandled hazard, or silent exception swallowing. |

## PIPELINE profile

| Field | Status and value |
|---|---|
| Layering | **FACT** — bronze, silver, and gold are Delta layers; bronze is raw, silver is typed/validated, and gold is business aggregates (`origin/tech-partnerships-solutions:infrastructure/terraform-databricks/main.tf:37-52`; `docs/tech-partnerships/runbook-databricks.md:100-115`). |
| Idempotency key | **PROPOSED** — restart with `MERGE` on a declared natural key plus `ns`; state the key in each unit contract. |
| Refresh mode | **PROPOSED** — use incremental processing where a reliable key exists, otherwise full refresh; each unit must state its choice. |
| Invalid data | **FACT** — reject/quarantine rows into a rescue table, never drop them or silently null them (`.migration/03_recon_tolerances.md:25-38`). |
| Quarantine accounting | **FACT** — compare both sides over the same population and report quarantine beside money comparisons (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:162-167`). |
| Logging | **PROPOSED** — structured job logging replaces `/var/log/etl/*.log`; failures remain visible and attributable. |
| Exceptions | **FACT** — no equivalent of `WHEN OTHERS THEN NULL`; swallowed failures are a migration hazard (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:117-118`; `services/legacy-billing/db/oracle/schema/04_jobs.sql:19-28`). |
| Pipeline drift rules | **PROPOSED** — reject a PR for non-idempotent restart behavior, an unstated refresh mode, missing rescue/count accounting, silent drops/nulling, unstructured-only logs, or swallowed exceptions. |

## ORCHESTRATION profile

| Field | Status and value |
|---|---|
| Source schedules | **FACT** — two disabled `DBMS_SCHEDULER` jobs exist: nightly dunning at 02:00 and audit purge at 03:30 (`services/legacy-billing/db/oracle/schema/04_jobs.sql:8-28`; `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:27-39`). |
| Batch chain | **FACT** — the crontab and `run_all.sh` chain are workload sources (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:81-87`). |
| Target | **PROPOSED** — map scheduler jobs and the crontab/`run_all.sh` chain to Databricks Workflows. |
| Dependencies | **PROPOSED** — use real task dependencies; never use `sleep` as a dependency. |
| Concurrency | **PROPOSED** — `max_active_runs=1` for each workflow. |
| Failure handling | **PROPOSED** — bounded retries and failure alerting are required; a failed task must not report success. |
| Schedule state | **PROPOSED** — schedules land `PAUSED` in this shared workspace and are unpaused only at cutover. |
| Orchestration drift rules | **PROPOSED** — reject a PR for a sleep dependency, absent dependency edge, overlap risk, unbounded retry, missing failure alerting, or an unpaused schedule. |

## CONSUMER profile

| Field | Status and value |
|---|---|
| Known report | **FACT** — the finance report is the known consumer output (`etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md:1-80`; `docs/tech-partnerships/billing-report-contract.md:24-50`). |
| Target output | **PROPOSED** — publish a gold Delta aggregate plus a scheduled export honoring `docs/tech-partnerships/billing-report-contract.md`. |
| Recipients | **FACT** — recipients are managed configuration in the `ow_tp` secret scope, never hardcoded; the legacy list is stale (`origin/tech-partnerships-solutions:infrastructure/terraform-databricks/jobs_finance_report.tf:8-18,33-39`). |
| Table readers | **PROPOSED** — re-point a consumer that only reads a table rather than rebuilding it. |
| Coverage warning | **FACT** — D4-1 is `UNMAPPED` and D4-2 closed by decision: no audit observation window; this profile covers only known consumers (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:157-160,196-224`). |
| Consumer drift rules | **PROPOSED** — reject a PR for changed report JSON/cent semantics, hardcoded recipients, an undocumented consumer, a claim that no consumers exist, or omission of the D4-1/D4-2 warning. |

## ML-SCORING profile

| Field | Status and value |
|---|---|
| Applicability | **FACT — N/A** — `OW_BILLING` contains no model training or scoring workload. The census is 20 tables, 5 packages, 2 scheduler jobs, 7 triggers, and 0 views (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:27-39`). |
| Implementation | **FACT — N/A** — do not invent an ML unit or profile for this estate. |
| Drift rules | **PROPOSED** — reject a PR that invents ML training/scoring scope without a new approved intake decision. |

## DATA/DEPENDENCY profile

| Field | Status and value |
|---|---|
| Coexistence | **FACT** — federation-first via Lakehouse Federation over JDBC to Oracle; customer-approved and recon mode is `LIVE` (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:138-145,153-154`). |
| Dual-write | **PROPOSED** — no dual-write. |
| PII | **FACT** — `CUSTOMER_MASTER` carries PII (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:226-230`). |
| Access control | **PROPOSED** — confirm masking and least privilege at STOP A. |
| Source retention | **FACT** — post-cutover Oracle retention/decommissioning is an open STOP E decision (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:255-259`). |
| Dependency access | **FACT** — targeted grants replaced `SELECT_CATALOG_ROLE`; AWR was deliberately not granted (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:178-194`). |
| Data/dependency drift rules | **PROPOSED** — reject a PR for a non-LIVE recon claim, dual-write, unapproved PII exposure, broad catalog grants, or a source-retention assumption presented as settled. |

## Cross-profile reconciliation

- **FACT** — money remains exact to the cent, while a bad date may quarantine a row; recon must compare the same source-minus-quarantine population on both sides and show the quarantine count next to every money comparison (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:162-167`; `.migration/03_recon_tolerances.md:25-38`).
- **FACT** — `LIVE` federation is the source comparison path, but the consumer census remains artifact-derived because D4-2 declined observation (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:77-93,138-145,196-224`).
- **PROPOSED** — pipeline and orchestration jobs must publish the namespace and structured run identifiers used by the recon report; consumer exports must read the same gold tables that recon checks.
- **PROPOSED** — SQL dictionary decisions control both pipeline typing and consumer aggregates; a child may not pass recon by changing a consumer-facing semantic independently.

## Open questions for STOP A and downstream stops

1. **PROPOSED — STOP A:** confirm masking and least-privilege rules for PII in `CUSTOMER_MASTER`.
2. **PROPOSED — STOP A:** confirm the existing serverless SQL warehouse name/data source and migration-principal scope.
3. **FACT — STOP B:** pipeline choice remains downstream; each unit must declare full refresh or incremental mode (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:255-260`).
4. **FACT — STOP E:** decide how long Oracle remains readable over federation after cutover (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:255-259`).
5. **FACT — accepted risk:** do not reopen consumer observation as a gate; D4-2 is closed by customer decision (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:196-224`).
