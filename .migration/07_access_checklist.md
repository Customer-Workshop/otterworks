# Access checklist

Probed 2026-09-14 by the orchestrator session (read-only). Evidence files live on the session VM
under `/home/ubuntu/probe/` and are summarised here; no credential value is recorded anywhere.

| # | Item | Status | Evidence (redacted) | If blocked |
|---|---|---|---|---|
| 1 | AWS Secrets Manager read of `ow-tp/oracle/ow_billing_ro` (us-east-1) with `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` | WORKS | keys `user,password,host,port,service,dsn` present | — |
| 2 | Oracle connection as `ow_billing_ro` (python-oracledb thin, `52.201.36.9:1521/FREEPDB1`) | WORKS | `SESSION_PRIVS` = `CREATE SESSION`, `SELECT ANY DICTIONARY`, `SELECT ANY TABLE`; no roles; no write privilege | — |
| 3 | Oracle live metadata query | WORKS | `DBA_OBJECTS` owner `OW_BILLING`: 20 TABLE, 25 INDEX, 5 PACKAGE, 5 PACKAGE BODY, 7 TRIGGER, 5 SEQUENCE, 2 JOB (69 objects, all VALID). Note: `ALL_*` views hide packages/triggers/sequences for this user (no EXECUTE grant); use `DBA_*` (allowed by `SELECT ANY DICTIONARY`). | — |
| 4 | Oracle seed verification | WORKS | `COUNT(*)`: `CUSTOMER_MASTER` 25 000, `INVOICE_HEADER` 18 750, `INVOICE_LINE` 150 000, `ENTITY_ATTR_VALUE` 8 333, demo tenants 60. `CURRENT_SCN` 2 142 013 (> seed SCN 2 137 574). `LOG_MODE=ARCHIVELOG`, `SUPPLEMENTAL_LOG_DATA_MIN=NO`. | — |
| 5 | Oracle package/trigger source (`DBA_SOURCE`, 754 lines) and write provenance | WORKS | live write-set identical to the static grep recorded in `00_context.md`; 13 FKs, 19 PKs, 6 UKs, 78 CHECKs; sequences `SEQ_CUSTOMER_MASTER`=125 000, `SEQ_ENTITY_ATTR_VALUE`=11 001 (cache 1000), others =1 | — |
| 6 | Oracle write attempt | not attempted (forbidden); privilege set proves read-only | — | — |
| 7 | Databricks CLI + PAT (`DATABRICKS_DEMO_HOST`, `DATABRICKS_DEMO_TOKEN`; `DATABRICKS_CLIENT_ID/SECRET` unset) | WORKS | `current-user me`: `dhrov.subramanian@cognition.ai`, groups `users`,`admins` (human PAT, workspace admin -> D10-4). Workspace `dbc-8bc9474f-40ae.cloud.databricks.com` | — |
| 8 | Serverless SQL warehouse | WORKS | `565cd2fd713738c4` "Serverless Starter Warehouse", `enable_serverless_compute=true`, state STOPPED (auto-starts) | — |
| 9 | Migration catalog objects | WORKS | `ow_tp` schemas `bronze`,`silver`,`gold`,`ops`(+`default`); volume `ow_tp.bronze.landing`; secret scope `ow_tp` | — |
| 10 | Target-catalog write capability | WORKS (parent evidence) | parent preflight manifest `databricks-capabilities.json` 11/11 verified (Files PUT/GET/DELETE in landing, temp schema create/delete, temp job create/delete, temp secret scope create/delete, warehouse). Not repeated by this session. | — |
| 11 | Lakebase project / branch metadata | WORKS | `projects/ow-tp-billing`, display `ow_tp-billing`, `pg_version 17`, default branch `production` (READY) | — |
| 12 | Lakebase credential + read-only connect | WORKS | `generate-database-credential` on `.../branches/production/endpoints/primary` returned a 1 h token (held in memory only); `psql` read: `PostgreSQL 17.11`, db `databricks_postgres`, schemas `public`, `__db_system`. Nothing written to `production`. | — |
| 13 | Lakebase branch create (per-batch namespace) | not attempted at setup (no write before STOP A) | will be exercised at wave 0 | — |
| 14 | Recon harness install | WORKS with workaround | system `setuptools 59.6.0` cannot build editable; installed user `setuptools>=68`, copied harness to `/home/ubuntu/dbx-harness`, `pip install --user --no-build-isolation -e ".[databricks,lakebase]"` | blueprint item |
| 15 | Recon harness self-test | WORKS | `dbx-recon selftest PASS: 9 canonicalization rules exercised` | — |
| 16 | Recon Oracle driver | BLOCKED | no `oracle` extra in harness (`databricks`, `sqlserver`, `lakebase`, `all`, `test`) -> D10-5 | wave-0 item |
| 17 | Databricks serverless -> Oracle network | BLOCKED | SG admits Devin CIDRs only -> D10-2; recon from Devin VM works (rows 2-5) | parent applies SG |
| 18 | Oracle supplemental logging / `c##dbzuser` | BLOCKED | `SUPPLEMENTAL_LOG_DATA_MIN=NO`; `DBA_USERS` has no `C##DBZUSER` -> D10-1 | customer DBA |
| 19 | Enforcement hook (`hooks/dbx_guard.py`) platform loading | BLOCKED | nonce probe echoed unblocked (`hook_platform_loaded: fail`); guard works when invoked directly -> D10-7 | org admin |

## D10-2 evidence: Databricks serverless egress
Full research note: `evidence/d10-2_serverless_egress.md`. Workspace region AWS us-west-2; CIDRs from
`https://www.databricks.com/networking/v1/ip-ranges.json` (snapshot 2026-09-07): `18.246.106.0/24`,
`3.42.138.0/25`, `44.234.192.32/28`, `52.27.216.188/32`. Not static; the doc requires re-reading the
JSON when it changes. Legacy NCC stable-IP list is decommissioned; NCC/PrivateLink not required.

## factory-doctor
Command and result recorded in `09_capabilities.json` (orchestrator role). Summary in `stops/STOP_A.md`.
