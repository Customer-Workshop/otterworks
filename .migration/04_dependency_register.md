# 04_dependency_register — what we need from humans

D10 = an external dependency that blocks work. Open D10s are entry criteria for the stop
that needs them; none of them is a reason to route around a guardrail.

| ID | Item | Blocks | Owner | Status | Notes |
|---|---|---|---|---|---|
| D10-01 | Security group `sg-0eaf11f4434260e1e`: open 1521 to the Databricks serverless NAT range (us-east-1) | live-mode recon for every Oracle-sourced unit; pipeline 1 STOP D | engagement owner | **OPEN — asked 2026-09-15** | The recon harness refuses the Oracle source adapter (shipped untested, raises before connecting). Lakehouse Federation read as `--family databricks` is the supported path. Without it recon runs DEGRADED on snapshots. |
| D10-02 | Lakebase project `ow-tp-billing` provisioned; DSN saved as `OW_TP_LAKEBASE_DSN` | every operational-track unit | parent (self-serve) | IN PROGRESS | `LAKEBASE_MIGRATION_DSN` points at the unrelated `loan-servicing-migration` project and must not be reused. |
| D10-03 | Kinesis on-demand stream + Debezium Server deployment on EKS `otterworks-dev` | the pipeline 1 CDC leg only | parent (self-serve) | PENDING | Debezium LogMiner against Oracle 26ai Free is outside the tested matrix. Fallback recorded in D-002. |
| D10-04 | Confirmation that the Databricks service principal `dhrov_spa` is the migration identity instead of the PAT | factory-doctor green; unattended children | engagement owner | **OPEN — asked 2026-09-15** | PAT resolves to a human user, which the doctor grades as blocking. Proceeding on the SP; reversible. |
| D3-01 | `MVSPROD` job `CB77340` keeps dropping `CUSTBILL*.dat` on SFTP: who repoints it, and does SFTP survive cutover | pipeline 2 cutover | engagement owner | UNDECIDED | Raised by the estate inventory. |
| D4-01 | The finance `.xls` email consumer is dead (sendmail pipe). Who consumes the month-end close today, and what artifact do they accept | pipeline 2 STOP C | engagement owner | UNDECIDED | D-008. Pipeline 2 has no acceptance criteria without it. |
| D5-01 | Two hand-maintained crontabs with overlapping schedules and orphan lock files; the cron box must be decommissioned by a human after Lakeflow Jobs land | pipeline 2 and 3 cutover | engagement owner | UNDECIDED | Raised by the estate inventory. |
| D6-01 | `pkg_ow_util` is shared by all four billing packages; owned by pipeline 1 wave 0 | pipeline 1 wave 1 | parent | PROPOSED | Shared-object map in the inventory. |
| D7-01 | `etl/config.ini` holds plaintext AWS keys, a Postgres password and a MeiliSearch key on the branch | pipeline 3 | engagement owner | UNDECIDED | Converted jobs reference secrets by name; rotating the exposed values is the customer's action. |
| D8-01 | Legacy tables have no foreign keys; orphan `INVOICE_LINE` rows and malformed strings are declared anomalies to reproduce, not clean | every pipeline 1 unit | parent | PROPOSED | Covered by `03_recon_tolerances.md`. |
| D9-01 | `INVOICES`/`INVOICE_LINES` (modern, 5 rows) vs `INVOICE_HEADER`/`INVOICE_LINE` (legacy, 168,750 rows) | every pipeline 1 unit | parent | PROPOSED | Each unit mapping must name which pair it migrates. |
| D10-05 | STOP E cutover authorization, per pipeline | cutover of each pipeline | engagement owner | NOT YET DUE | Never default-accepted. Devin never holds the cutover principal. |

## Closed

| ID | Item | Closed by |
|---|---|---|
| D10-00 | Source-side CDC prerequisites (ARCHIVELOG, supplemental logging, capture user) | Owner approved the one-time DDL; applied 2026-09-15 (D-001). |
