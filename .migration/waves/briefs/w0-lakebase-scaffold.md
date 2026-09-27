UNIT lakebase_scaffold (wave 0, serial, width 1). Stand up the Lakebase target schema and load the reference tables.
1. On Lakebase branch mig-20260927c-w0 create schema `billing` (idempotent) and typed DDL for CODES, PLANS, TENANTS,
   USAGE_EVENTS exactly as .migration/units/lakebase_scaffold/mapping_spec.json declares (PKs from the Oracle
   dictionary .migration/inventory/oracle_dictionary_20260927c.json). DDL lives in the repo under
   databricks/mig_20260927c/lakebase/00_scaffold.sql plus a small idempotent apply script.
2. Load those four tables from Oracle via the session bridge (python-oracledb read, psycopg COPY), whole tables,
   `ns::` prefixed demo tenants included. Touch no other billing table; wave 1 units own theirs.
3. Recon: dbx-recon run --family oracle --mode live --depth full ... PASS on all four objects. Also run
   dbx-recon fixture-shape against the fixture copy and dbx-recon type-map-audit on the mapping spec.
4. Gates you must satisfy: w0-structural (schema + tables exist with the declared types and PKs),
   w0-reference-parity (row_parity, depth full, PASS), w0-fixture-shape (fixture column shape equals the Oracle
   dictionary; fixture-shape exit 0).
Write targets: ow_tp.billing.codes, ow_tp.billing.plans, ow_tp.billing.tenants, ow_tp.billing.usage_events
(Lakebase branch mig-20260927c-w0 only). Deploy objects: none.

NOTES:
- Expected harness outcome: the harness PASS is the merge authority (plugin 0.4.3 treats first-hop
  platform-role grants as the platform's).
- Confirm your dbx-recon is >= 0.4.3 (tests dir has test_grants_inherited_through_a_platform_role_are_not_the_units)
  before the live recon; otherwise report FAIL "plugin_stale" without running.
- Guard rules learned in prior runs: literal -f for SQL files (no shell-expanded SQL args); split Oracle extract
  and psycopg load into two programs (extract | load); never `rm` a path starting with databricks/ (use git rm
  or python); no heredocs mentioning apply.sh or psql-like tokens; load OW_BILLING_RO_DSN from Secrets Manager
  in-process (a ~/bin helper outside the repo) instead of command-substitution exports.
- Use a de-qualified copy of the mapping spec (mapping_spec.bare.json under .migration/recon/lakebase_scaffold/):
  the Lakebase adapter needs schema-relative object names; fixture-shape --source-statement-cap 40.
