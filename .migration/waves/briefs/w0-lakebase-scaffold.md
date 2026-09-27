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
