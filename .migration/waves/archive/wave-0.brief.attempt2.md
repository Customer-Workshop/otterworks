# Wave 0 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w0-lakebase-scaffold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 4, 'tier2': 4, 'tier3': 12, 'tier4': 0, 'total': 20}, target_statements={'tier1': 4, 'tier2': 4, 'tier3': 8, 'tier4': 0, 'total': 16}, source_rows_fetched=926, target_rows_fetched=926; actual source_statements=53, target_statements=38, source_rows_fetched=918, target_rows_fetched=918, harness time 12s. Verifier depth full, overrides: w0-lakebase-scaffold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- An open PR #1729 for the same branch already existed from attempt 1, so it was taken over and updated rather than duplicated.
- Doctor rewrites .migration/09_capabilities.json in a child; needed git restore after every run to keep the ledger untouched.
- Doctor warns recon_harness: databricks-sql-connector missing; irrelevant for a Lakebase (postgres adapter) target but not documented as such.
- Fixture-mode recon needs the local Oracle fixture (make oracle-billing-up + oracle-billing-seed NS=demo); it FAILs by design on fixture-only trigger/extra rows and is dev evidence only.
- Guard rejects $VAR in command position and any wrapper in front of dbx-recon/doctor except a ~/bin python helper invoked as python3 /abs/helper.py <client>; derived by trial.
- LAKEBASE_MIGRATION_DSN / OW_BILLING_FIXTURE_DSN env-var names for loader, recon --target-secret and fixture-shape --fixture-dsn-secret are not in the brief; recovered from prior self_check.md. Lakebase DSN can omit the password since libpq reads ~/.pgpass.

Per batch:
- w0-lakebase-scaffold: FAIL. PASS downgraded: changed_paths not verifiable from git (not a PR of this repo, or its fetch or diff failed), ledger integrity unverified; lakebase_scaffold re-applied and reloaded on mig-20260927c-w0 (918 rows), live recon PASS depth full, all 3 gates passed, merge_eligible=false (rerun_unsupported) under human override D-016; PR #1729 updated, CI green (6/6). https://github.com/Cognition-Partner-Workshops/otterworks/pull/1729
