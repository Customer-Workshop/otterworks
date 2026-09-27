UNIT lakebase_scaffold (wave 0, serial, width 1). Stand up the Lakebase target schema and load the reference tables.
1. On Lakebase branch mig-20260927-w0 create schema `billing` (idempotent) and typed DDL for CODES, PLANS, TENANTS,
   USAGE_EVENTS exactly as .migration/units/lakebase_scaffold/mapping_spec.json declares (PKs from the Oracle
   dictionary .migration/inventory/oracle_dictionary_20260927.json). DDL lives in the repo under
   databricks/mig_20260927/lakebase/00_scaffold.sql plus a small idempotent apply script.
2. Load those four tables from Oracle via the session bridge (python-oracledb read, psycopg COPY), whole tables,
   `ns::` prefixed demo tenants included. Touch no other billing table; wave 1 units own theirs.
3. Recon: dbx-recon run --family oracle --mode live --depth full ... PASS on all four objects. Also run
   dbx-recon fixture-shape against the fixture copy and dbx-recon type-map-audit on the mapping spec.
4. Gates you must satisfy: w0-structural (schema + tables exist with the declared types and PKs),
   w0-reference-parity (row_parity, depth full, PASS), w0-fixture-shape (fixture column shape equals the Oracle
   dictionary; fixture-shape exit 0).
Write targets: ow_tp.billing.codes, ow_tp.billing.plans, ow_tp.billing.tenants, ow_tp.billing.usage_events
(Lakebase branch mig-20260927-w0 only). Deploy objects: none.

RUN 3 NOTES (after run 2, D-035, closed FAIL missing_rule):
- Branch mig/20260927/w0-lakebase-scaffold and PR #1727 already exist from run 2 with the scaffold DDL, loader and
  recon evidence. Reuse them: rebase or reset that branch onto the current base, push there, and update PR #1727
  (first line PASS/FAIL). Do NOT open a second PR.
- The objects already exist on mig-20260927-w0; apply.sh must be idempotent (drop/recreate the four tables + schema
  billing) before the load and the live recon.
- A human recorded merge_override for lakebase_scaffold as D-036 in .migration/06_decisions.md covering exactly two
  harness gaps: Lakebase platform-inherited grants reported as grant_extra, and rerun proof unsupported for a
  first-run scaffold. If the final live recon fails on those two findings only (rows tiers 1-3 PASS), report
  merge_authority {kind: human_override, decision_id: D-036}. Any other finding is a real FAIL.
- Run 2 evidence is in .migration/recon/lakebase_scaffold/ on that branch (mapping_spec.bare.json, fresh_shape.json):
  reuse the de-qualified mapping copy and use run 2's fresh_shape.json as the prior shape for the rerun proof.
  fixture-shape --source-statement-cap 40.

RUN 4 NOTES (after run 3, D-037, closed FAIL; plugin fixed in dbx-migration-plugin PR #71 / v0.4.2):
- Run 3 notes still apply for branch/PR reuse and idempotent apply.sh, but the D-036 override path is gone: the
  harness now excludes grantees that inherit through a Lakebase platform role, so grant_extra must not appear and
  merge_authority must be the harness verdict PASS. Confirm your dbx-recon is >= 0.4.2 (the platform-role test
  `test_grants_inherited_through_a_platform_role_are_not_the_units` exists in its tests dir) before the live recon;
  if it is not, report FAIL "plugin_stale" without running.
- Rerun proof must have a real evolved leg. Do NOT reuse run 2's fresh_shape.json as --prior-shape (it equals the
  fresh shape and the harness rejects it). Instead add databricks/mig_20260927/lakebase/00_scaffold.prior.sql: the
  four tables at a declared earlier shape (same columns and PKs, but without uq_plans_code, uq_tenants_name and
  fk_usage_tenant, and codes.code_desc as varchar(40)), apply it on mig-20260927-w0 first, record that as pre_shape (dbx-recon
  rerun-proof ... --prior-shape from that DDL), then run apply.sh (which drop/recreates to the current DDL) and let
  the evolved leg prove it converges on the fresh shape. Commit prior DDL + rerun/*.json under the unit's evidence
  dir. If the harness still says evolved unsupported, that is a real FAIL: report the reason string verbatim.
