# 07 — Access checklist (verified 2026-09-01, NS=cdw)

Raw probe evidence kept outside the repo (`/home/ubuntu/intake-cdw/`); no credential values recorded anywhere.

## Legacy source — Oracle (`FREEPDB1`, schema `COMMISSION_DW`)
| Check | Result | Notes |
|---|---|---|
| Instance up (`make insurance-up NS=cdw`) | VERIFIED | container `otterworks-insurance-cdw-insurance-oracle-1`, healthy, listener `127.0.0.1:51992` (loopback-only) |
| Read as `commission_dw` (metadata + data) | VERIFIED | `ALL_OBJECTS`, `ALL_TAB_COLUMNS`, `ALL_INDEXES`, `ALL_SOURCE`, `ALL_MVIEWS`, `COUNT(*)` on all 9 objects |
| Read `COMMISSION_PAY` feed tables | VERIFIED | AGENTS 4, PRODUCTS 3, POLICIES 5, COMMISSION_LEDGER 0 rows |
| Object census | 5 tables (incl. MV container), 1 MV, 1 package + body, 4 sequences, 9 unique indexes | matches intake |
| Table stats (`NUM_ROWS`) | not populated | counts taken directly |
| **Current DW row counts** | **all 0** (`DIM_*`, `FACT_COMMISSION`, MV) — the loader has never run in this instance and the ledger is empty | → baseline population question at STOP A (see `06_decisions.md` DEC-011) |
| Query history (`V$SQL`, AWR, audit) | NOT GRANTED | D10-3 accepted; not requestable |
| Scheduler | none | D5-1 |
| DDL/DML by us | NEVER | policy; the only writes to legacy are its own loader/refresh run by the legacy's own procedures during baseline population, if approved |
| Concurrency | ≤2 read sessions | tolerance record v1 |

## Target — Databricks (workspace at `DATABRICKS_DEMO_HOST`)
`make tp-preflight-databricks` → **7/10 VERIFIED, 3 DENIED** (all three because catalog `ow_tp` does not exist).
| Probe | Result |
|---|---|
| serverless-warehouse `565cd2fd713738c4` (Serverless Starter Warehouse) | VERIFIED, RUNNING |
| jobs-create-list / jobs-delete | VERIFIED |
| secret-scope create / delete | VERIFIED |
| files-delete | VERIFIED |
| uc-create-list (schema in `ow_tp`) | DENIED — `NO_SUCH_CATALOG_EXCEPTION` |
| files-get-directory / files-put-get (volume in `ow_tp`) | DENIED — 404, catalog absent |
| uc-schema-delete | VERIFIED (nothing to delete) |
| `SHOW CATALOGS` | ok; `ow_tp` absent (D10-2 → wave 0 creates it, preflight re-run must reach 10/10 before any child launches) |
| `SHOW CONNECTIONS` | ok; no connection to the source exists or can exist (loopback) → D10-1 confirmed |
| Statement Execution API | VERIFIED (used for the SHOW statements) |
| Cluster creation | FORBIDDEN by policy (not probed) |

## Repo / tooling
| Check | Result |
|---|---|
| Run branch fetched, worktree `/home/ubuntu/repos/ow-run` | VERIFIED |
| `make tp-validate-schemas`, `tp-validate-recon`, `tp-fixture-land/verify`, `tp-smoke` targets present | VERIFIED |
| Legacy source SQL in repo | `services/industry-solutions/insurance/db/olap/01_star_schema.sql`, `02_etl_pkg.sql`, `setup/01_users.sql` |
| Consumer code sweep (`COMMISSION_DW`, `MV_AGENT_COMMISSION_SUMMARY`, `DW_ETL_PKG`) | only the schema's own definition/test files reference them — no application consumer found (D4-1 remains an evidence gap, not a finding of "none") |

## Slack
`#ow-migrations` C0BQP3P965V, `#ow-tp-alerts` C0BQP3LU3JT, `#ow-tp-status` C0BRYRE5ZQQ — read/write VERIFIED.

## Lead-time requests fired
None required: every gap is either self-serve (create `ow_tp`) or accepted (query history, federation).
