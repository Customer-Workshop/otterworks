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

RERUN NOTES (run 20260927b, attempt 2 after the HALT recorded as D-016; STOP C row D-017):
- Branch mig/20260927b/w0-lakebase-scaffold and PR #1728 exist from attempt 1 of THIS run: check them out, keep
  the existing DDL/apply.sh/extract/load code and evidence layout, push new commits to the same branch and keep
  that one PR (update its description; first line PASS or FAIL). Do not open a second PR.
- mig-20260927b-w0 already holds schema billing + the four tables from attempt 1. apply.sh is idempotent
  (drop/recreate): redo the full sequence so the evidence is fresh: apply prior DDL (00_scaffold.prior.sql) ->
  pre_shape, apply.sh current -> evolved leg, drop + apply.sh current -> fresh leg, reload the four tables from
  Oracle via the session bridge, then the live recon (--mode live --depth full) and fixture-shape / type-map-audit.
  Commit rerun/*.json, dependencies.json ({routines: []}), fixture_shape, type_map_audit and live/ evidence.
- Expected harness outcome: tiers 1-3 PASS and tier 0 FAIL only with grant_extra for a grantee whose privilege
  comes solely through membership in a Lakebase platform role (databricks_superuser, granted by the platform event
  trigger on_create_table_or_view). That exact finding class is covered by ledger row D-018 (merge_override
  lakebase_scaffold; waive w0-structural lakebase_scaffold): report status PASS with merge_authority
  {kind: human_override, decision_id: D-018}, report gate w0-structural as failed with the result.json evidence
  (the workflow applies the waiver from the ledger) and state in the gate evidence that types/PKs/uniques/FKs
  match. Never write to .migration/06_decisions.md. Any other finding class (type, PK, count, keyed diff, a grant
  to any grantee that is NOT platform-inherited) is a real FAIL: report it as such.
- Confirm your dbx-recon is >= 0.4.2 (tests dir has test_grants_inherited_through_a_platform_role_are_not_the_units)
  before the live recon; otherwise report FAIL "plugin_stale" without running.
- Guard rules learned in attempt 1: literal -f for SQL files (no shell-expanded SQL args); split Oracle extract
  and psycopg load into two programs (extract | load); never `rm` a path starting with databricks/ (use git rm
  or python); no heredocs mentioning apply.sh or psql-like tokens; load OW_BILLING_RO_DSN from Secrets Manager
  in-process (a ~/bin helper outside the repo) instead of command-substitution exports.
- Use a de-qualified copy of the mapping spec (mapping_spec.bare.json under .migration/recon/lakebase_scaffold/):
  the Lakebase adapter needs schema-relative object names; fixture-shape --source-statement-cap 40.
