# OW_BILLING target state (pipeline 1, monthly invoicing)

Status: PROPOSED, confirmed at STOP A (see `.migration/stops/STOP_A.md`). Marks: FACT / DISCOVERED / PROPOSED as in `.migration/00_context.md`.

## CORE
| Field | Value | Mark |
|---|---|---|
| Workspace | `dbc-8bc9474f-40ae.cloud.databricks.com` (AWS us-west-2), via `DATABRICKS_DEMO_HOST` | DISCOVERED |
| Migration catalog | `ow_tp` (bronze / silver / gold / ops), volume `/Volumes/ow_tp/bronze/landing` | FACT |
| Identity | PAT `DATABRICKS_DEMO_TOKEN`, human workspace-admin user (D10-4; SP option at STOP A) | DISCOVERED |
| Compute | existing serverless SQL warehouse `565cd2fd713738c4`; serverless jobs/pipelines; no clusters | FACT |
| Table format | Delta, Unity Catalog managed tables; legacy names preserved lowercase | PROPOSED |
| Isolation | per-batch schemas `ow_tp.<schema>__p1w<N>_<unit>` (Delta) and Lakebase branch `mig-p1-w<N>-<batch>` | PROPOSED |
| Deploy | Declarative Automation Bundles, target `migration`; `prod`/`production` targets forbidden from any child | PROPOSED |

## SQL (analytical-track procedures, views, scheduled queries)
| Field | Value | Mark |
|---|---|---|
| Dialect | Databricks SQL (DBR 17+ scripting, `CREATE PROCEDURE` where a like-for-like port is needed) | PROPOSED |
| Oracle constructs | `NVL`->`COALESCE`, `DECODE`->`CASE`, `SYSDATE`->`current_timestamp()`, `ROWNUM`->`LIMIT`/window, `(+)` joins -> ANSI, `CONNECT BY` -> recursive CTE, `NUMBER(p,s)`->`DECIMAL(p,s)`, `VARCHAR2`->`STRING`, `DATE`->`TIMESTAMP` (second precision), `DD-MON-YY` strings kept as strings with a parsed companion column | PROPOSED (`oracle-plsql`) |
| Case sensitivity | Oracle identifiers upper -> lowercased; `COLLATE UTF8_LCASE` not needed (Oracle compares case-sensitively) | PROPOSED |

## PIPELINE (analytical loads)
| Field | Value | Mark |
|---|---|---|
| Engine | Lakeflow Spark Declarative Pipelines (serverless) for the `INVOICE_HEADER`/`INVOICE_LINE`/`*_HIST` landings and the CUSTBILL/analytics surfaces later | PROPOSED |
| Load | SCN-pinned freeze-and-load (`AS OF SCN <pin>`) via JDBC pull from the Devin VM path until D10-2 opens the serverless path | FACT |
| Quality | expectations for planted anomalies: `expect_or_drop` never used; anomalies routed to `ow_tp.ops.quarantine_<unit>` | FACT |

## ORCHESTRATION
| Field | Value | Mark |
|---|---|---|
| Jobs | Lakeflow Jobs `ow_tp_<unit>`, `ns` parameter (`demo`), schedules PAUSED until STOP E | FACT |
| Legacy schedules | `JOB_NIGHTLY_DUNNING` 02:00, `JOB_PURGE_AUDIT_LOG` 03:30 (both disabled at source) -> D5-1, decided at STOP C | DISCOVERED |
| Alerts | job failure -> parent's `#ow-tp-alerts` (parent-owned) | PROPOSED |

## CONSUMER
| Field | Value | Mark |
|---|---|---|
| Applications | billing service and any pool holding an `OW_BILLING` connection (D4-1 census in inventory) -> repoint to Lakebase Postgres wire protocol at STOP E, customer executes | PROPOSED |
| Reports / batch | CUSTBILL, analytics cron, `UsageRollupJob` -> read `ow_tp.silver`/`gold` (pipelines 2/3) | FACT |
| Repoint PR | one PR changing connection config only, prepared by Devin, executed by the customer with the cutover principal | FACT |

## LAKEBASE (operational track)
| Field | Value | Mark |
|---|---|---|
| Tier / version | Lakebase Postgres Autoscaling, PostgreSQL 17 (live: 17.11) | DISCOVERED |
| Project / branch / endpoint / db | `projects/ow-tp-billing` / `production` (default, never written by migration) / `primary` / `databricks_postgres` | FACT |
| Migration namespace | one branch per wave batch `mig-p1-w<N>-<batch>` off `production`, copy-on-write, TTL 72 h, dropped at wave close; schema `ow_billing` inside the branch | PROPOSED |
| Credential | `databricks postgres generate-database-credential .../branches/<branch>/endpoints/primary`, 1 h, in memory only; logical `LAKEBASE_OW_TP_BILLING_DSN` | FACT |
| Schema mapping | `NUMBER(p,s)`->`NUMERIC(p,s)`; `NUMBER` (no scale) -> `NUMERIC`/`BIGINT` by observed values; `VARCHAR2(n)`->`VARCHAR(n)`; `DATE`->`TIMESTAMP(0)`; `CLOB`->`TEXT`; `CHAR(1) Y/N` kept as `CHAR(1)` with CHECK | PROPOSED |
| Constraints / indexes | all 19 PK, 6 UK, 13 FK, 78 CHECK, 25 indexes recreated 1:1; target-only additions accepted | PROPOSED |
| Sequences / identity | `SEQ_*` -> Postgres sequences restarted at source `LAST_NUMBER`+cache at the pin; `TRG_*_SEQ` before-insert triggers -> `DEFAULT nextval()` (identity contract row in the unit mapping) | PROPOSED |
| Triggers | `trg_*_hist` -> PL/pgSQL AFTER triggers; `trg_sub_no_uncancel`, `trg_usage_events_check` -> PL/pgSQL BEFORE triggers; `pkg_ow_util.log_msg` autonomous transaction -> `dblink`-free pattern: audit rows written by the caller inside the same tx, with a documented semantic delta row | PROPOSED |
| Packages | `pkg_plans`, `pkg_rating`, `pkg_invoicing`, `pkg_dunning`, `pkg_ow_util` -> PL/pgSQL functions/procedures in schema `ow_billing`, package state (`g_*` variables) -> session settings or explicit parameters (dictionary row per variable) | PROPOSED |
| Isolation | Oracle statement-level read consistency -> Postgres `READ COMMITTED` (same default class); procedures relying on `SELECT ... FOR UPDATE` keep row locks | PROPOSED |
| Connectivity | Postgres wire protocol, OAuth token or generated credential; app repoint = host/db/user/password change | FACT |
| Lakehouse sync | Lakebase synced tables -> `ow_tp.silver.<table>` (continuous) feed the analytical track and pipelines 2/3 | PROPOSED |

## DATA / DEPENDENCY
| Field | Value | Mark |
|---|---|---|
| Operational load | Debezium (Oracle LogMiner) -> Kafka -> Delta landing -> Lakebase apply (intake decision); alternative surfaced at STOP A: Lakeflow Connect Oracle integrated CDC connector (managed, needs the same D10-1 supplemental logging, removes D10-3 Kafka hosting, lands in Delta only so a Lakebase apply step remains) | FACT / PROPOSED (alternative) |
| Rehearsal fallback | SCN-pinned freeze-and-load into the Lakebase branch while D10-1 is open | FACT |
| Consistency pin | `V$DATABASE.CURRENT_SCN` at load start; every unit's mapping carries `scn` | PROPOSED |
| Source access | read-only `ow_billing_ro` (CREATE SESSION, SELECT ANY TABLE, SELECT ANY DICTIONARY); use `DBA_*` views | DISCOVERED |

## ML-SCORING
N/A: no model consumers in `OW_BILLING`.
