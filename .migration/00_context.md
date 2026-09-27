# 00 — Engagement context (run 20260927)

Every field is FACT (with its source) or PROPOSED (for a stop). Nothing is silently blank.

## Identity of this run

| Field | Value | Status |
|---|---|---|
| Repo | `Cognition-Partner-Workshops/otterworks` | FACT — user brief |
| Immutable source branch | `tech-partnerships` | FACT — user brief; `scripts/tp-run-branch.sh` |
| `base_branch` (run branch; every unit PR targets it) | `tp-run/databricks-20260927T122304Z` | FACT — `make tp-run-branch TRACK=databricks` output |
| `trunk_base_decision` | N/A — `main` / `tech-partnerships` are never targeted | FACT — AGENTS.md, topology policy |
| `run_id` | `20260927` | FACT — this file; prefixes every Databricks / Lakebase object |
| `stop_mode` | **hard** for every stop (A, B, C, E); wave close is a notification | FACT — user: "message me on slack only at stops, wave closes, or a halt" and "I'll decline the repoint at STOP E" |
| `auto_merge` | false (hard mode requires it) | FACT — contract.md |
| Merge owner | orchestrator (this session) merges PASS PRs into the run branch after each wave-close notice | FACT — user brief |
| Notification contract | Slack, channel #dbx-migration (C09ETT31F0S) via the Slack integration; one message per stop, wave close, halt; never per child | FACT — user brief; prior-run channel |
| Interaction contract | live demo; approvals by Slack reply in the stop thread | FACT — user brief |
| Migration principal (Databricks) | service principal `DE-shared`, applicationId `d9d1c4ec-29da-4ec7-9aa0-e932710d61e2`, id `70843528212943`, `DATABRICKS_AUTH_TYPE=oauth-m2m`, host `https://dbc-8bc9474f-40ae.cloud.databricks.com`; no PAT in children | FACT — `databricks current-user me` (session) |
| Admin PAT | used **only** by `make tp-demo-reset APPLY=1 ORACLE=…` (reset + Oracle boot); never in `.migration/`, children or PRs | FACT — user brief |
| Source principal | Oracle `OW_BILLING_RO` on `52.201.36.9:1521/FREEPDB1` (EC2 `i-0be201ad6412c5e5e`), secret **name** `ow-tp/oracle/ow_billing_ro` (AWS Secrets Manager, us-east-1), exported at run time as `OW_BILLING_RO_DSN` | FACT — `07_access_checklist.md` |
| Oracle posture | read-only in every phase: no CDC, no supplemental logging, no Debezium, no 1521 to serverless, no Lakehouse Federation | FACT — user brief |

## Business scope (one vertical slice, one tenant)

| Item | Value | Status |
|---|---|---|
| Slice | signup -> subscription -> `issue_invoice` -> nightly CUSTBILL fixed-width file -> finance close total on a dashboard | FACT — user brief |
| Legacy estate | Oracle `OW_BILLING` (20 tables, packages `pkg_ow_util`, `pkg_plans`, `pkg_rating`, `pkg_invoicing`, `pkg_dunning`) + ksh/Perl CUSTBILL chain (`etl/legacy-extra/`: `oracle_custbill_extract.py` -> `parse_custbill_fixedwidth.sh` -> `finance_excel_report.pl` -> finance CSV -> `legacy-billing GET /api/reports/finance`) | FACT — repo, live catalog read |
| Fixture tenant | `00000000-0000-0000-0000-000000000001` "Tenant One": STARTER plan, subscription status 10, one usage event (2026-02-10, 260 units), three closed rating periods (Nov 2025-Jan 2026, rollover 100 each), **no invoice yet**; billing period `2026-02-01 .. 2026-02-28` | FACT — live read of `tenants`/`subscriptions`/`usage_events`/`rating_periods`/`invoices` (static seed rows, identical in the local fixture) |
| Databricks target — operational | Lakebase project `ow-tp-billing`, branches `mig-20260927-w<n>` (unit work, TTL 7d) and `mig-20260927-exec` (routine-parity exec branch, TTL 7d), schema `billing`; production branch never touched | FACT — user brief; PROPOSED at STOP A: the `-exec` branch name |
| Databricks target — analytical | catalog `ow_tp`, schemas `mig_20260927_bronze / _silver / _gold / _quarantine`, volume `ow_tp.mig_20260927_bronze.landing`, jobs/pipelines `ow_tp_20260927_*` (PAUSED), warehouse `565cd2fd713738c4`, one AI/BI dashboard `ow_tp_20260927_finance_close` | FACT — user brief |
| Off limits | `ow_tp.bronze/silver/gold`, `airbyte_demo`, `fivetran_*`, Lakebase `production` | FACT — user brief |
| Findings only (no migration) | analytics crons (`etl/legacy-extra/jobs/*.cron`, `04_jobs.sql` scheduler jobs, all disabled), the Scala job | FACT — user brief |
| Cutover | STOP E is blocking; the user has pre-announced a decline; children never cut over; schedules land PAUSED | FACT — user brief |

## Target profiles (per workload; approved at STOP A)

| Workload | Profile | Migration shape | Recon shape |
|---|---|---|---|
| PL/SQL packages `pkg_ow_util`, `pkg_plans`, `pkg_rating`, `pkg_invoicing` | **OLTP-ROUTINES** on Lakebase (`billing.fn_*` / `billing.sp_*` matching `services/legacy-billing/app/backends/postgres.py`) | convert from `services/legacy-billing/db/oracle/packages/*.sql`; behaviour preserved incl. `log_msg` autonomous audit write (D-009) | `dbx-recon routine-parity` on the `-exec` branch against the fixture golden set + `dbx-recon --family oracle` table parity of the state tables |
| `pkg_dunning` | **PROPOSED: not in scope** unless `04_dependency_register.md` shows a call edge from the slice | — | — |
| Reference/state tables the routines read and write (`codes`, `plans`, `tenants`, `subscriptions`, `usage_events`, `rating_periods`, `rating_results`, `invoices`, `invoice_lines`, `credit_notes`, `billing_audit_log`) | **REFERENCE-LOAD** into Lakebase `billing.*` (one-shot, Oracle read-only) | typed DDL + load from Oracle via the session bridge | `dbx-recon --family oracle --mode live`, exact |
| CUSTBILL chain (`invoice_header`, `invoice_line`, `customer_master`, `entity_attr_value` -> fixed-width file -> finance CSV) | **BATCH-PIPELINE**: Lakeflow Spark Declarative Pipeline `ow_tp_20260927_custbill` with expectations + `mig_20260927_quarantine` tables, bronze landing volume, silver typed tables, gold `mig_20260927_gold.finance_close` | file contract preserved byte-for-byte (D7) | CUSTBILL SHA-256 equality (custom gate) + `dbx-recon` on silver/gold vs Oracle/legacy CSV |
| Finance close total | **BI-SURFACE**: one AI/BI dashboard on `mig_20260927_gold.finance_close` | dashboard JSON committed under `databricks/` | close total side by side with legacy CSV total |
| Analytics crons, Scala job | N/A — findings in `02_inventory.md` | — | — |
| ML scoring | N/A — none in the estate | — | — |

## Evidence contract (STOP E packet)

Legacy output, Databricks output, `dbx-recon` verdict, side by side, for: the Tenant One invoice row, the CUSTBILL SHA-256, the finance close total. Three recordings (legacy flow, Databricks flow, live `issue_invoice` on Lakebase) by the testing agent once each side is green. Run branch, unit PRs, verifier packet, recon reports, dashboard link, one-screen "what moved". SI comparison qualitative only.
