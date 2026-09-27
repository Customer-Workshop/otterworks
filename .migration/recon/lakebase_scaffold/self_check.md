# tp-pre-pr-self-check: lakebase_scaffold (wave 0, run 20260927)

Evidence for each item; nothing below is described as green without a path.

- NULL / missing attribution: every column is NOT NULL in both the Oracle dictionary and
  `00_scaffold.sql`; `load_reference.normalize` rejects unexpected types rather than coercing.
  Recon tier 2/3 PASS on all 19 fields (`result.json`).
- Namespace scoping: all writes go to `ow_tp.billing.{codes,plans,tenants,usage_events}` on
  Lakebase branch `mig-20260927-w0`; `load_reference.py` refuses any target database other than
  `ow_tp` and truncates only those four tables.
- No shared table is dropped/replaced/altered by the DDL: the DROP/CREATE in `00_scaffold.sql`
  covers only the four unit-owned tables (and `billing` itself only when the schema is empty).
  Run 3's fresh leg dropped and recreated exactly those tables on the migration branch
  (`rerun/fresh_apply.log`); run 2's `CREATE ... IF NOT EXISTS` form was replaced by
  drop/recreate so a rerun lands the declared shape.
- Retention / cleanup: the loader is a whole-table truncate-and-reload of reference data inside
  one transaction; there is no run-scoped data to lose.
- Cleanup retains evidence: nothing under `.migration/recon/lakebase_scaffold/` is removed by any
  script.
- Secrets: DSNs are read from env var names (`OW_BILLING_RO_DSN`, `LAKEBASE_MIGRATION_DSN`), the
  Lakebase token lives in `~/.pgpass` only; no value appears in source, evidence, or commits.
  The grantee `dhrov.subramanian@cognition.ai` in recon findings is a workspace admin role name
  read from the Lakebase catalog, not a distribution list.
- Parity vs tolerance: `tol-20260927-v1` used unchanged; no tolerance edited.
- Idempotency proven by an actual rerun (run 3): `rerun/fresh_apply.log` (drop/recreate onto the
  run-2 shape) then `rerun/evolved_apply.log` (second apply, same drop/recreate, shape identical),
  graded in `rerun/rerun_proof.json` (fresh pass; evolved `unsupported` because the pre_shape
  equals the fresh shape — drop/recreate means nothing evolves). `rerun/fresh_shape.json` and
  `rerun/evolved_shape.json` are the harness shape reads; `prior_digest` now equals
  `shape_digest`.
- Recon values recomputed from the target platform by `dbx-recon run --mode live --depth full`
  (`result.json`, `report.md`, `recon.summary.md`); run 3 used 1 live attempt (total 4 across
  runs), tiers 1-3 PASS on all 918 keyed rows; tier 0 fails only on the platform grant below.
- Unverified paths: none in the loader. Unresolved recon findings are listed in `result.json`.
- Machine-readable report: `result.json` is the harness's own schema (no `*.recon.json` used).
- Capability preflight (run 3): child doctor ready=True, 12 ok / 1 warn / 1 skipped — the warn is
  the advisory `type_map_audit` (child-level; the orchestrator gates it), the skip is
  `named_secrets_exist` (none referenced). First attempt failed on missing `oracledb` for the
  system python and an untrusted `mise.toml`; rerun under the dbxrecon venv after `mise trust`
  passed. `.migration/09_capabilities.json` restored to HEAD afterwards.
- `make tp-smoke`: green (6 passed, "tp-smoke: all checks passed").

## Contractual coverage gaps (why merge_eligible=false)

1. `structural_gap` / `grant_extra` on all four tables: Lakebase grants every table to the
   platform role `databricks_superuser`, whose members include `pg_write_all_data` and the
   workspace admin `dhrov.subramanian@cognition.ai`. `REVOKE ALL ... FROM databricks_superuser`
   (in the DDL) does not remove the privilege because it arrives through `pg_write_all_data`
   membership, which is a platform role the unit may not alter. The harness has no rule for
   platform-inherited grants (failure_class `missing_rule`).
2. `rerun_unsupported`: the evolved leg needs a shape change between pre and post; the scaffold
   is drop/recreate, so pre_shape always equals post shape and the leg is honestly `unsupported`
   (a committed prior shape now exists — `prior_digest == shape_digest` — and it changes nothing).
