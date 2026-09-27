# 07 — Access checklist (run 20260927)

Every row is a probe that ran from this session, with the command shape and the result. Secret values never appear here.

| # | Access | Principal / secret (name only) | Probe | Result | Status |
|---|---|---|---|---|---|
| 1 | Oracle `OW_BILLING` read-only | `OW_BILLING_RO` via AWS Secrets Manager `ow-tp/oracle/ow_billing_ro` (us-east-1) -> env `OW_BILLING_RO_DSN` | `SELECT privilege FROM session_privs` / `SELECT granted_role FROM user_role_privs` / `SELECT COUNT(*) FROM all_tables WHERE owner='OW_BILLING'` (python-oracledb thin, `52.201.36.9:1521/FREEPDB1`) | privileges `CREATE SESSION`, `SELECT ANY TABLE`, `SELECT ANY DICTIONARY`, `FLASHBACK ANY TABLE`; **no roles, no write privilege**; 20 tables, 25 indexes visible; `ALL_SOURCE` empty (no PL/SQL source readable) | BLOCKED at STOP A: factory-doctor `source_principal_read_only` = fail (`FLASHBACK ANY TABLE` is beyond SELECT-only; D-023). Reads work; the factory will not launch children on this principal until the grant is revoked or a customer-signed attestation row exists. |
| 2 | Oracle instance | EC2 `i-0be201ad6412c5e5e`, admin PAT path via `make tp-demo-reset APPLY=1 ORACLE=…` only | reset output | instance running, `52.201.36.9:1521` reachable, zero stale `ow_tp_*` / `mig_*` / `mig-*` objects | OK |
| 3 | Databricks workspace identity | SP `DE-shared` `d9d1c4ec-29da-4ec7-9aa0-e932710d61e2`, `DATABRICKS_AUTH_TYPE=oauth-m2m`, `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` (env, by name) | `databricks current-user me` | `userName` = applicationId, `id 70843528212943`, host `https://dbc-8bc9474f-40ae.cloud.databricks.com` | OK |
| 4 | Unity Catalog `ow_tp` | same SP | `databricks schemas list ow_tp`; `CREATE SCHEMA ow_tp.mig_20260927_probe` is left to the doctor's `analytical_target_grants` row | existing schemas: `_fivetran_setup_test, airbyte_demo, default, fivetran_metadata, fivetran_trimester_remoteness_staging, information_schema`; no `mig_20260927_*` present | OK (grants row in `09_capabilities.json`) |
| 5 | SQL warehouse | `565cd2fd713738c4` | `databricks warehouses get 565cd2fd713738c4` | `RUNNING` | OK |
| 6 | Lakebase project | `ow-tp-billing`, branch create/delete | doctor `lakebase_branch_create` (one-hour `dbx-doctor-probe-*` child of `production`, deleted) | see `09_capabilities.json` | pending doctor |
| 7 | Lakebase migration branch DSN | `LAKEBASE_MIGRATION_DSN` (generated at run time with `databricks postgres generate-database-credential`, never stored) on `mig-20260927-w0` | doctor `lakebase_target_grants` (`has_database_privilege(..., 'CREATE')`) | see `09_capabilities.json` | pending doctor |
| 8 | Guard hook | `hooks/dbx_guard.py` PreToolUse | nonce probe `__dbx_guard_probe__<nonce>` | see `09_capabilities.json` `hook_guard` | pending doctor |
| 9 | Recon harness | `~/.venvs/dbx-recon/bin/dbx-recon` (oracledb + psycopg + databricks-sql extras) | `dbx-recon selftest` | 9 canonicalization rules OK | OK |
| 10 | Local Oracle fixture | docker `otterworks-oracle-billing-oracle-billing-1`, `localhost:52521/FREEPDB1`, `ow_billing` (dev password in compose file, not a secret) | `make oracle-billing-up && make oracle-billing-seed NS=demo` | healthy; packages VALID; static tenants 1..9 identical to the estate | OK |
| 11 | Slack | `#ow-migrations` (C0BQP3P965V) via the Slack integration; `#dbx-migration` (C09ETT31F0S) from the prior run is not accessible to this session | `lookup_slack_resource` + `list_channels`; STOP A posted https://cogpartners.slack.com/archives/C0BQP3P965V/p1790513601122399 | read+write | OK |
| 12 | Cutover principal | not held, never requested | — | STOP E pre-declined by the user | N/A |

Blocked-by-default rules: row 1 failing (a write privilege or a role) blocks STOP A; nothing here downgrades to fixture or local access silently (`08_connectivity.json` records the resolved posture).
