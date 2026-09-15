# Governance inventory — OW_BILLING

One row per (object, grantee, privilege/policy). Credentials are never recorded here, only
the fact that an account exists and what it holds.

## Grants on in-scope objects

| Object | Grantee | Privilege | Grantable | Evidence |
|---|---|---|---|---|
| `OW_BILLING` (schema) | PUBLIC | INHERIT PRIVILEGES | NO | FACT(live) `ALL_TAB_PRIVS where table_schema='OW_BILLING'` |

That single row is the complete result of the grant query at the read-only principal's
privilege level. No object-level grants to any named user or role exist on the 20 tables.

## Accounts

| Account | Type | Holds | Evidence |
|---|---|---|---|
| `OW_BILLING` | schema owner | owns all 20 tables, 25 indexes, 5 sequences, 7 triggers, 5 packages, 2 scheduler jobs | FACT(live) + FACT(admin-probe) |
| `OW_BILLING_RO` | read-only reader (migration source principal) | SELECT on the 20 tables; `CREATE TABLE` probe fails ORA-01031 | FACT(live) write probe |
| `C##DBZUSER` | CDC capture common user | LOGMINING, SELECT ANY TRANSACTION, SELECT ANY TABLE, FLASHBACK ANY TABLE, LOCK ANY TABLE, SET CONTAINER, CREATE SESSION, CREATE TABLE, CREATE SEQUENCE | FACT(admin-probe) |
| Oracle admin | superuser | used once for the D-001 supplemental-logging DDL, never again | FACT(admin-probe) |

Secret names only (values never recorded): `ow-tp/oracle/ow_billing_ro`,
`ow-tp/oracle/dbzuser`, `ow-tp/oracle/admin`.

## Roles, masking, row-level policies

`DBA_ROLES`, `DBA_ROLE_PRIVS` and the redaction-policy views are not readable by the
read-only principal, so role membership and any masking/redaction policy on in-scope
objects are **UNVERIFIABLE** at this access tier. Recorded as unverifiable rather than
implied absent. If the engagement needs the grant story to be complete before cutover,
that is a one-off admin-credential read, and it is a user decision to authorize it.

## Findings

- `etl/config.ini` carries plaintext AWS access keys, a Postgres password and a
  MeiliSearch master key on the branch (D7-01). Converted jobs reference secrets by name;
  rotating the exposed values is the customer's action, not the migration's.
- Supplemental logging is enabled on 19 of 20 tables (`FIXTURE_META` excluded) under the
  user's explicit D-001 override. No further Oracle writes are authorized.
