# tp-pre-pr-self-check: lakebase_scaffold (wave 0, run 20260927)

Evidence for each item; nothing below is described as green without a path.

- NULL / missing attribution: every column is NOT NULL in both the Oracle dictionary and
  `00_scaffold.sql`; `load_reference.normalize` rejects unexpected types rather than coercing.
  Recon tier 2/3 PASS on all 19 fields (`result.json`).
- Namespace scoping: all writes go to `ow_tp.billing.{codes,plans,tenants,usage_events}` on
  Lakebase branch `mig-20260927-w0`; `load_reference.py` refuses any target database other than
  `ow_tp` and truncates only those four tables.
- No shared table is dropped/replaced/altered by the DDL (`CREATE ... IF NOT EXISTS` only). The
  fresh rerun leg dropped and recreated only the four unit-owned tables on the migration branch
  (`rerun/fresh_apply.log`).
- Retention / cleanup: the loader is a whole-table truncate-and-reload of reference data inside
  one transaction; there is no run-scoped data to lose.
- Cleanup retains evidence: nothing under `.migration/recon/lakebase_scaffold/` is removed by any
  script.
- Secrets: DSNs are read from env var names (`OW_BILLING_RO_DSN`, `LAKEBASE_MIGRATION_DSN`), the
  Lakebase token lives in `~/.pgpass` only; no value appears in source, evidence, or commits.
  The grantee `dhrov.subramanian@cognition.ai` in recon findings is a workspace admin role name
  read from the Lakebase catalog, not a distribution list.
- Parity vs tolerance: `tol-20260927-v1` used unchanged; no tolerance edited.
- Idempotency proven by an actual rerun: `rerun/fresh_apply.log` (empty schema) then
  `rerun/evolved_apply.log` (second apply, all relations skipped), graded in
  `rerun/rerun_proof.json` (fresh pass; evolved `unsupported` because no prior committed shape
  exists for a first-run scaffold).
- Recon values recomputed from the target platform by `dbx-recon run --mode live --depth full`
  (`result.json`, `report.md`, `recon.summary.md`); 3 live attempts, all identical.
- Unverified paths: none in the loader. Unresolved recon findings are listed in `result.json`.
- Machine-readable report: `result.json` is the harness's own schema (no `*.recon.json` used).
- Capability preflight: child doctor passed before any live work (`.migration/09_capabilities.json`
  restored to HEAD afterwards; the doctor rewrites it).
- `make tp-smoke`: green (6 passed, "tp-smoke: all checks passed").

## Contractual coverage gaps (why merge_eligible=false)

1. `structural_gap` / `grant_extra` on all four tables: Lakebase grants every table to the
   platform role `databricks_superuser`, whose members include `pg_write_all_data` and the
   workspace admin `dhrov.subramanian@cognition.ai`. `REVOKE ALL ... FROM databricks_superuser`
   (in the DDL) does not remove the privilege because it arrives through `pg_write_all_data`
   membership, which is a platform role the unit may not alter. The harness has no rule for
   platform-inherited grants (failure_class `missing_rule`).
2. `rerun_unsupported`: the evolved leg needs a previously committed shape; wave 0 creates the
   tables for the first time, so no prior shape exists and the leg is honestly `unsupported`.
