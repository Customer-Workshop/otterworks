# 02 — Glossary

| Term | Definition |
|---|---|
| CUSTBILL | **FACT** — the fixed-width billing feed processed by the legacy ETL chain; the target migration contracts describe its bronze landing and typed silver records (`origin/tech-partnerships-solutions:databricks/notebooks/custbill_sql.py:11-21,55-91`). |
| EAV / `ENTITY_ATTR_VALUE` | **FACT** — entity-attribute-value storage in the Oracle estate; its typed-column/pivot treatment is a central dictionary decision (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:112-118`). |
| Dunning | **FACT** — overdue-account collection/suspension processing, scheduled by `JOB_NIGHTLY_DUNNING` at 02:00 (`services/legacy-billing/db/oracle/schema/04_jobs.sql:8-17`). |
| Rating | **FACT** — usage calculation and finalization exposed by `PKG_RATING` (`services/legacy-billing/db/oracle/packages/03_pkg_rating.sql:1-27`). |
| `PKG_*` | **FACT** — Oracle PL/SQL packages that hold the estate's procedural business logic; the census found five packages (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:27-39`). |
| `_HIST` tables | **FACT** — trigger-capture history tables that preserve full-row copies, including `CUSTOMER_MASTER_HIST` and `SUBSCRIPTIONS_HIST` (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:115-118`; `services/legacy-billing/db/oracle/schema/02_horror.sql:1-20`). |
| `ns` / namespace | **FACT** — per-run isolation key; jobs accept it, volume paths include it, and table rows carry it (`docs/tech-partnerships/contracts/README.md:27-29`). |
| `ow_tp` | **FACT** — shared-workspace isolation prefix, catalog name, job-name prefix, secret scope, and notebook-root component (`docs/tech-partnerships/contracts/README.md:15-26`). |
| Wave | **PROPOSED** — an ordered group of migration units released after the pilot and governed by STOP D. |
| Unit | **FACT** — one coherent migration item such as a PL/SQL package, scheduler job, trigger rule, or load/report script (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:120-137`). |
| Batch | **PROPOSED** — one execution of a unit or workflow for one namespace and run identifier. |
| D1–D10 | **PROPOSED taxonomy** — dependency-register categories: D1 source/data availability; D2 schema/metadata; D3 transformation semantics; D4 consumer/reader coverage; D5 target/platform capability; D6 security/identity; D7 orchestration/operations; D8 data quality/reconciliation; D9 retention/cutover; D10 external approval/access. |
