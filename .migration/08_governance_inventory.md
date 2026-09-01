# 08 — Governance inventory (`COMMISSION_DW`, census 2026-09-01)

| # | Kind | Grantee / principal | Object | Privilege / policy | Status | Evidence |
|---|---|---|---|---|---|---|
| G1 | grant | `PUBLIC` | `COMMISSION_DW` (schema user) | `INHERIT PRIVILEGES` (Oracle default, not data access) | FACT | `ALL_TAB_PRIVS WHERE table_schema IN (…)` |
| G2 | grant | `PUBLIC` | `COMMISSION_PAY` (schema user) | `INHERIT PRIVILEGES` (default) | FACT | same |
| G3 | system privs | `COMMISSION_DW` | — | `CREATE SESSION/TABLE/VIEW/SEQUENCE/PROCEDURE/MATERIALIZED VIEW` | FACT | `USER_SYS_PRIVS` |
| G4 | roles | `COMMISSION_DW` | — | none | FACT | `USER_ROLE_PRIVS` (0 rows) |
| G5 | object grants received | `COMMISSION_DW` | `COMMISSION_PAY.*` | none via `USER_TAB_PRIVS_RECD` (0 rows); reads succeed → access is via schema-level grant or same-owner setup in `setup/01_users.sql` | FACT (rows) / INFERRED (mechanism) | `USER_TAB_PRIVS_RECD`; `setup/01_users.sql` |
| G6 | masking / RLS | — | `COMMISSION_DW.*`, `COMMISSION_PAY.*` | none | FACT | `ALL_POLICIES` (0 rows) |
| G7 | service accounts | — | — | none beyond the two schema owners | FACT | `ALL_TAB_PRIVS` |

Target mapping (for cutover, D8-1): no grants to reproduce for consumers (none exist); target grants = engagement principals only, `SELECT` on `ow_tp.gold.*_cdw`; no UC masks. Coverage: 2 grant rows, both accounted to P1.
