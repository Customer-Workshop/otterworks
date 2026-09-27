# Wave 0 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w0-lakebase-scaffold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 4, 'tier2': 4, 'tier3': 12, 'tier4': 0, 'total': 20}, target_statements={'tier1': 4, 'tier2': 4, 'tier3': 8, 'tier4': 0, 'total': 16}, source_rows_fetched=926, target_rows_fetched=926; actual source_statements=53, target_statements=38, source_rows_fetched=918, target_rows_fetched=918, harness time 5s. Verifier depth full, overrides: w0-lakebase-scaffold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- The guard blocks TRUNCATE/COPY on a psycopg connection built from an env-var DSN; the loader must pass the allowlisted host/db literally (password via ~/.pgpass) so the target is statically resolvable.
- The local Oracle fixture (make oracle-billing-up + oracle-billing-seed NS=demo) is needed for fixture-shape; DSN oracle://ow_billing:ow_billing@localhost:52521/[REDACTED SECRET] as OW_BILLING_FIXTURE_DSN.
- The session environment already exports a LAKEBASE_MIGRATION_DSN pointing at a different Lakebase endpoint/database (databricks_postgres); the helper must overwrite it, not setdefault, or dbx-recon refuses with a target-identity error.
- dbx-recon fixture-shape/run --out is a directory, not a file path.
- dbx-recon run refuses a stale --rerun-proof after any --rerun-source edit; regrade with dbx-recon rerun-proof (no connections) before the live run, and it does not consume a live attempt.
- doctor's databricks identity check fails until `mise trust` is run in the repo; wrapper scripts in front of the databricks CLI are blocked by the guard (run the CLI bare).

Per batch:
- w0-lakebase-scaffold: FAIL. PASS downgraded: gate w0-structural evidence '.migration/recon/lakebase_scaffold/result.json (tier 0, 4/4); .migration/recon/lakebase_scaffold/rerun/fresh_shape.json' is not a file under .migration/recon/<unit>/ of lakebase_scaffold at the gated PR head; gate w0-reference-parity evidence '.migration/recon/lakebase_scaffold/result.json (live, depth full, PASS, 918 rows)' is not a file under .migration/recon/<unit>/ of lakebase_scaffold at the gated PR head; gate w0-fixture-shape evidence '.migration/recon/lakebase_scaffold/fixture_shape.json (pass, exit 0, 24/40 statements)' is not a file under .migration/recon/<unit>/ of lakebase_scaffold at the gated PR head; gate w0-structural (structural) is pending; gate w0-reference-parity (row_parity) is pending; gate w0-fixture-shape (custom) is pending; lakebase_scaffold landed on mig-20260927c-w0: billing schema + 4 typed reference tables loaded (918 rows), live full recon PASS, all 3 gates passed; merge_eligible=false only for rerun_unsupported under human override D-016; PR #1729 updated, CI 6/6 green, not merged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1729
