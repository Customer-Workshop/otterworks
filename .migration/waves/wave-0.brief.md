# Wave 0 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w0-lakebase-scaffold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 4, 'tier2': 4, 'tier3': 12, 'tier4': 0, 'total': 20}, target_statements={'tier1': 4, 'tier2': 4, 'tier3': 8, 'tier4': 0, 'total': 16}, source_rows_fetched=926, target_rows_fetched=926; actual source_statements=53, target_statements=38, source_rows_fetched=918, target_rows_fetched=918, harness time 5s. Verifier depth full, overrides: w0-lakebase-scaffold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- Drop/recreate makes rerun proof 'evolved' structurally unsupported (pre-shape == fresh shape); harness needs a drop-recreate rerun mode rather than relying on D-036.
- Guard treats --force-with-lease on a unit branch as protected-history rewrite; had to merge base forward + cherry-pick instead of rebase — the brief should say 'merge forward', not 'rebase or reset'.
- Harness has no way to classify Lakebase platform-inherited grants (pg_write_all_data via databricks_superuser) as expected; grant_extra needs a platform-grant allowlist.
- factory-doctor must run as python -m doctor from the recon venv (system python lacks oracledb) and mise.toml needs trusting for the databricks shim.
- result.json cannot carry a human_override authority; the child has to translate D-036 into the report by hand.

Per batch:
- w0-lakebase-scaffold: FAIL. PASS downgraded: recon evidence was live/FAIL; lakebase_scaffold run 3: billing schema + 4 tables drop/recreated on mig-20260927-w0, 918 rows reloaded, live recon rows tiers 1-3 PASS; harness FAIL only on D-036's two gaps (grant_extra x4, rerun evolved unsupported) → human_override D-036; PR #1727 updated, not merged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1727
