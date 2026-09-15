# 07_access_checklist — who we are and what we can touch

Names only. No values appear here or in any artifact.

## Identities

| Role | Identity | Auth | Verified |
|---|---|---|---|
| Migration principal (Databricks) | service principal `2e90bc1d-e9a1-4703-8c48-ad28ebb1864d` (display name `dhrov_spa`) | OAuth M2M — `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`, host `DATABRICKS_HOST` | yes — `databricks current-user me` |
| Fallback (not used) | PAT `DATABRICKS_DEMO_TOKEN` on `DATABRICKS_DEMO_HOST` | personal access token, resolves to a human user | rejected for unattended work (D-005) |
| Source reader | Oracle `OW_BILLING_RO` | AWS Secrets Manager `ow-tp/oracle/ow_billing_ro` | yes — connects; `CREATE TABLE` probe fails ORA-01031 |
| Source admin | Oracle admin | `ow-tp/oracle/admin` | used once, for the approved DDL in D-001, and never again |
| CDC capture | Oracle `C##DBZUSER` | `ow-tp/oracle/dbzuser` | privileges verified: LOGMINING, SELECT ANY TRANSACTION, SELECT ANY TABLE, FLASHBACK ANY TABLE, SET CONTAINER |
| Operational target | Lakebase project `ow-tp-billing` | DSN under the name `OW_TP_LAKEBASE_DSN` | pending provisioning (D10-02) |
| Cutover principal | held by the engagement owner | — | Devin never holds or requests it |

## Write scope

Allowlisted: catalog `ow_tp` (schemas `bronze`, `silver`, `gold`), the volume
`/Volumes/ow_tp/bronze/landing`, and the Lakebase database `ow_tp` / schema `billing` on
non-production `mig-*` branches. Everything else is denied by `allowed_targets.json` and the
guard hook.

Explicitly out of scope: any Oracle object (one recorded exception, D-001), the Lakebase
`production` branch, the `loan-servicing-migration` project, the `tech-partnerships` branch,
and any catalog other than `ow_tp`.

## Verified capability surface

`make tp-preflight PLATFORM=databricks`, 2026-09-15: 11 probes, 0 denied — volume files
get/put/delete, Unity Catalog schema create/list/delete, Jobs create/list/delete, secret
scope create/delete, and the serverless warehouse `565cd2fd713738c4` (STOPPED, starts on
demand). Manifest: `.tp-preflight/databricks-capabilities.json`. That manifest is evidence of
raw API capability only; `.migration/09_capabilities.json` from factory-doctor is the
authority for whether a wave may launch.

## Network

Oracle `52.201.36.9:1521` is reachable from Devin sessions. Databricks serverless cannot
reach it: `sg-0eaf11f4434260e1e` allows 1521 from Devin egress ranges only. That is D10-01,
and it is what decides whether recon runs live or degraded.
