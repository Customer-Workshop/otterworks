# 04_dependency_register — what we need from humans

D10 = an external dependency that blocks work. Open D10s are entry criteria for the stop
that needs them; none of them is a reason to route around a guardrail.

| ID | Item | Blocks | Owner | Status | Notes |
|---|---|---|---|---|---|
| D10-01 | Security group `sg-0eaf11f4434260e1e`: open 1521 to the Databricks serverless NAT range (us-east-1) | live-mode recon for every Oracle-sourced unit; pipeline 1 STOP D | engagement owner | **OPEN — asked 2026-09-15** | The recon harness refuses the Oracle source adapter (shipped untested, raises before connecting). Lakehouse Federation read as `--family databricks` is the supported path. Without it recon runs DEGRADED on snapshots. |
| D10-02 | Lakebase project `ow-tp-billing` provisioned; DSN saved as `OW_TP_LAKEBASE_DSN` | every operational-track unit | parent (self-serve) | IN PROGRESS | `LAKEBASE_MIGRATION_DSN` points at the unrelated `loan-servicing-migration` project and must not be reused. |
| D10-03 | Kinesis on-demand stream + Debezium Server deployment on EKS `otterworks-dev` | the pipeline 1 CDC leg only | parent (self-serve) | PENDING | Debezium LogMiner against Oracle 26ai Free is outside the tested matrix. Fallback recorded in D-002. |
| D10-04 | Confirmation that the Databricks service principal `dhrov_spa` is the migration identity instead of the PAT | factory-doctor green; unattended children | engagement owner | **OPEN — asked 2026-09-15** | PAT resolves to a human user, which the doctor grades as blocking. Proceeding on the SP; reversible. |
| D10-05 | STOP E cutover authorization, per pipeline | cutover of each pipeline | engagement owner | NOT YET DUE | Never default-accepted. Devin never holds the cutover principal. |

## Closed

| ID | Item | Closed by |
|---|---|---|
| D10-00 | Source-side CDC prerequisites (ARCHIVELOG, supplemental logging, capture user) | Owner approved the one-time DDL; applied 2026-09-15 (D-001). |
