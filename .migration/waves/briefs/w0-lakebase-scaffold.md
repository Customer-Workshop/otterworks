UNIT lakebase_scaffold (wave 0, serial, width 1). Stand up the Lakebase target schema and load the reference tables.
1. On Lakebase branch mig-20260927b-w0 create schema `billing` (idempotent) and typed DDL for CODES, PLANS, TENANTS,
   USAGE_EVENTS exactly as .migration/units/lakebase_scaffold/mapping_spec.json declares (PKs from the Oracle
   dictionary .migration/inventory/oracle_dictionary_20260927b.json). DDL lives in the repo under
   databricks/mig_20260927b/lakebase/00_scaffold.sql plus a small idempotent apply script.
2. Load those four tables from Oracle via the session bridge (python-oracledb read, psycopg COPY), whole tables,
   `ns::` prefixed demo tenants included. Touch no other billing table; wave 1 units own theirs.
3. Recon: dbx-recon run --family oracle --mode live --depth full ... PASS on all four objects. Also run
   dbx-recon fixture-shape against the fixture copy and dbx-recon type-map-audit on the mapping spec.
4. Gates you must satisfy: w0-structural (schema + tables exist with the declared types and PKs),
   w0-reference-parity (row_parity, depth full, PASS), w0-fixture-shape (fixture column shape equals the Oracle
   dictionary; fixture-shape exit 0).
Write targets: ow_tp.billing.codes, ow_tp.billing.plans, ow_tp.billing.tenants, ow_tp.billing.usage_events
(Lakebase branch mig-20260927b-w0 only). Deploy objects: none.

FIRST-RUN NOTES (run 20260927b is a fresh run: no prior branch, PR, evidence or override exists; D-007):
- Open branch mig/20260927b/w0-lakebase-scaffold and exactly one PR into the base branch. mig-20260927b-w0 is empty
  (database ow_tp, no schema billing yet); apply.sh must still be idempotent (drop/recreate the four tables + schema
  billing) so the loader and the live recon can be repeated.
- merge_authority must be the harness verdict PASS; there is no human override in this run. Confirm your dbx-recon is
  >= 0.4.2 (the platform-role test `test_grants_inherited_through_a_platform_role_are_not_the_units` exists in its
  tests dir) before the live recon; if it is not, report FAIL "plugin_stale" without running. Lakebase
  platform-inherited grants must not appear as grant_extra with that version; if they do, that is a real FAIL.
- Rerun proof needs a real evolved leg. Add databricks/mig_20260927b/lakebase/00_scaffold.prior.sql: the four tables
  at a declared earlier shape (same columns and PKs, but without uq_plans_code, uq_tenants_name and fk_usage_tenant,
  and codes.code_desc as varchar(40)); apply it on mig-20260927b-w0 first, record that as pre_shape (dbx-recon
  rerun-proof ... --prior-shape from that DDL), then run apply.sh (drop/recreate to the current DDL) and let the
  evolved leg prove it converges on the fresh shape. Commit prior DDL + rerun/*.json under the unit's evidence dir.
  If the harness says evolved unsupported, that is a real FAIL: report the reason string verbatim.
- Use a de-qualified copy of the mapping spec (mapping_spec.bare.json under .migration/recon/lakebase_scaffold/) if
  the harness needs schema-relative object names on Lakebase; fixture-shape --source-statement-cap 40.
