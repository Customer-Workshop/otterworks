# 08 Governance inventory: OW_BILLING (Oracle Free 23ai, FREEPDB1)

Census date 2026-09-14, read-only principal `OW_BILLING_RO` (`ORACLE_OW_BILLING_RO_DSN`). Every row is FACT from the cited `DBA_*` query (`/home/ubuntu/probe/oracle_census.py`, results in `.migration/evidence/census/`). Credential values are never recorded; only that a principal exists.

## Non-Oracle-maintained principals (`DBA_USERS WHERE oracle_maintained='N'`)

| User | Status | Common | Created | Purpose (INFERRED from grants) |
|---|---|---|---|---|
| C##DBZUSER | OPEN | YES | 2026-09-14 19:40:40 | Debezium LogMiner CDC reader (created by the parent for D10-1); secret `ow-tp/oracle/dbzuser` |
| OW_BILLING | OPEN | NO | 2026-09-14 18:54:47 | schema owner (application principal, used by legacy jobs and the billing service) |
| OW_BILLING_RO | OPEN | NO | 2026-09-14 18:57:41 | migration read-only principal (`ORACLE_OW_BILLING_RO_DSN`) |
| PDBADMIN | OPEN | NO | 2026-09-14 18:44:23 | PDB administrator (customer DBA) |

## System privileges (`DBA_SYS_PRIVS`)

| Grantee | Privilege | Admin |
|---|---|---|
| C##DBZUSER | CREATE SEQUENCE | NO |
| C##DBZUSER | CREATE SESSION | NO |
| C##DBZUSER | CREATE TABLE | NO |
| C##DBZUSER | FLASHBACK ANY TABLE | NO |
| C##DBZUSER | LOCK ANY TABLE | NO |
| C##DBZUSER | LOGMINING | NO |
| C##DBZUSER | SELECT ANY TABLE | NO |
| C##DBZUSER | SELECT ANY TRANSACTION | NO |
| C##DBZUSER | SET CONTAINER | NO |
| OW_BILLING | CREATE JOB | NO |
| OW_BILLING | CREATE PROCEDURE | NO |
| OW_BILLING | CREATE SEQUENCE | NO |
| OW_BILLING | CREATE SESSION | NO |
| OW_BILLING | CREATE TABLE | NO |
| OW_BILLING | CREATE TRIGGER | NO |
| OW_BILLING | CREATE TYPE | NO |
| OW_BILLING | CREATE VIEW | NO |
| OW_BILLING_RO | CREATE SESSION | NO |
| OW_BILLING_RO | SELECT ANY DICTIONARY | NO |
| OW_BILLING_RO | SELECT ANY TABLE | NO |

## Roles (`DBA_ROLE_PRIVS`)

| Grantee | Role | Admin |
|---|---|---|
| C##DBZUSER | EXECUTE_CATALOG_ROLE | NO |
| C##DBZUSER | SELECT_CATALOG_ROLE | NO |
| PDBADMIN | PDB_DBA | YES |

## Object grants on OW_BILLING objects (`DBA_TAB_PRIVS WHERE owner='OW_BILLING'`)

**0 rows.** No object-level grants exist; every non-owner reader relies on `SELECT ANY TABLE`. Target implication: Lakebase roles must be created explicitly (owner role `ow_billing_app`, reader role `ow_billing_ro`), there is nothing to port 1:1.

## Policies

- VPD/RLS (`DBA_POLICIES`): 0 rows. - Data redaction (`REDACTION_POLICIES`): 0 rows. - Unified audit policies enabled (`AUDIT_UNIFIED_ENABLED_POLICIES`): 6 (Oracle defaults; none OW_BILLING-specific). - Views / materialized views / synonyms in OW_BILLING: 0 / 0 / 0.

## CDC posture (`V$DATABASE`, `DBA_LOG_GROUPS`)

- LOG_MODE=ARCHIVELOG, SUPPLEMENTAL_LOG_DATA_MIN=YES, PK=NO, ALL=NO (database level; per-table ALL COLUMN groups below), CURRENT_SCN at census 2149687.
- ALL COLUMN LOGGING (ALWAYS) present on: BILLING_AUDIT_LOG, CREDIT_NOTES, DUNNING_ATTEMPTS, INVOICES, INVOICE_LINES, NOTIFICATIONS, RATING_PERIODS, RATING_RESULTS, SUBSCRIPTIONS, TENANTS (10 tables = the operational write set). Confirms parent's D10-1 closure live.

## Findings for the register

- **D10-8 (new):** `OW_BILLING_RO` lacks `FLASHBACK ANY TABLE`: `SELECT ... AS OF SCN` fails with ORA-41900, so SCN-pinned freeze-and-load reads cannot use flashback queries from this principal. Workaround in use: `SET TRANSACTION READ ONLY` gives a statement-consistent snapshot within one session (consistency window recorded by `CURRENT_SCN` at open/close). Owner: customer DBA / parent (grant `FLASHBACK ANY TABLE` to `OW_BILLING_RO`) if cross-session SCN pinning is required by the analytical track.
- Coverage arithmetic counts these governance objects: 4 principals, 20 system-privilege rows, 3 role rows, 0 object grants, 0 policies, 10 supplemental log groups.
