# tp-pre-pr-self-check: lakebase_scaffold (wave 0, run 20260927c)

Evidence for each item; nothing below is described as green without a path.

- NULL / missing attribution: every column is NOT NULL in both the Oracle dictionary and
  `databricks/mig_20260927c/lakebase/00_scaffold.sql`; `extract_reference.render` rejects
  unexpected source types (floats, bools) instead of coercing, and the loader refuses a stream
  whose trailer counts differ from the rows it copied. Recon tiers 2/3 PASS on all 19 fields /
  918 keyed rows (`result.json`).
- Namespace scoping: all writes go to `ow_tp.billing.{codes,plans,tenants,usage_events}` on
  Lakebase branch `mig-20260927c-w0`; `load_reference.py` refuses any target database other than
  `ow_tp` and truncates only those four tables.
- No shared table is dropped/replaced/altered: the DROP/CREATE in `00_scaffold.sql` covers only
  the four unit-owned tables (and `billing` itself only when the schema is otherwise empty).
  `rerun/fresh_apply.log` shows the fresh apply on an empty branch.
- Retention / cleanup: the loader is a whole-table truncate-and-reload of reference data inside
  one transaction; there is no run-scoped data to lose.
- Cleanup retains evidence: nothing under `.migration/recon/lakebase_scaffold/` is removed by any
  script.
- Secrets: DSNs are read by env var name (`OW_BILLING_RO_DSN`, `LAKEBASE_MIGRATION_DSN`,
  `OW_BILLING_FIXTURE_DSN`); the Lakebase token lives in `~/.pgpass` only; no value appears in
  source, evidence, or commits. The extract stream is piped, never written to disk.
- Parity vs tolerance: `tol-20260927c-v1` used unchanged; no tolerance edited.
- Idempotency proven by an actual rerun: `rerun/fresh_apply.log` (apply on empty branch) then
  `rerun/evolved_apply.log` (second apply onto the fresh shape), graded by `dbx-recon rerun-proof`
  in `rerun/rerun_proof.json`: fresh `pass`, evolved `unsupported` (pre_shape equals the fresh
  shape: drop/recreate of an unchanged declared shape evolves nothing). `rerun/prior_proof_20260927.json`
  is the previous committed proof for this unit (same shape digest).
- Recon values recomputed from the target platform by `dbx-recon run --mode live --depth full`
  (`result.json`, `report.md`, `recon.summary.md`); D-017 rerun: apply.sh + extract | load re-executed
  on `mig-20260927c-w0`, then one live attempt of the allowed three (PASS, 918 keyed rows).
- Unverified paths: none in the loader. Fixture-mode recon (`fixture/`) FAILs on fixture-only
  differences (fixture trigger `TRG_USAGE_EVENTS_CHECK`, one extra fixture tenant and three
  extra fixture usage_events); it is development evidence only.
- Machine-readable report: `result.json` is the harness's own schema (no `*.recon.json` used).
- Capability preflight: child doctor `ready=True`, 11 ok / 2 warn (`type_map_audit`, advisory;
  `recon_harness`: databricks-sql-connector absent, irrelevant to a Lakebase target) / 1 skipped. `.migration/09_capabilities.json` unchanged.
- `make tp-smoke`: green (6 passed, "tp-smoke: all checks passed").
- Also run: `type_map_audit.json` (19 fields ok), `fixture_shape.json` (status pass, exit 0,
  24/40 source statements).

## Contractual coverage gap (why merge_eligible=false)

`rerun_unsupported`: the harness requires an evolved leg whose pre-shape differs from the fresh
shape. The declared shape of this unit has not changed since the prior committed proof, so no
honest evolved leg exists; drop/recreate lands the identical shape. Tiers 0-3 PASS and no other
block reason remains.
