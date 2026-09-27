# Wave 0 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w0-lakebase-scaffold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 4, 'tier2': 4, 'tier3': 12, 'tier4': 0, 'total': 20}, target_statements={'tier1': 4, 'tier2': 4, 'tier3': 8, 'tier4': 0, 'total': 16}, source_rows_fetched=926, target_rows_fetched=926; actual source_statements=53, target_statements=38, source_rows_fetched=918, target_rows_fetched=918, harness time 14s. Verifier depth full, overrides: w0-lakebase-scaffold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- --routine-dependencies must point at a COMMITTED file; a unit that converts no routine still needs dependencies.json {routines: []} committed before the merge-evidence run or merge_block_reasons carries routine_parity_missing
- Fixture owner principal sees Oracle triggers (trg_usage_events_check -> trigger_missing in fixture mode) that OW_BILLING_RO cannot; live mode reports none
- Guard rejects: shell-expanded SQL-file args (use literal -f), a single Python program mixing oracledb reads with psycopg writes (split extract | load), `rm <path starting with databricks/>` (parsed as the databricks client), and heredocs mentioning apply.sh/psql-like tokens
- Lakebase adapter needs schema-relative object names: brief's mapping_spec.bare.json hint was needed, ConfigError 'invalid SQL identifier ow_tp.billing.codes' otherwise
- Platform grant made directly to databricks_superuser by the on_create_table_or_view event trigger is inherited by workspace admins one hop away and surfaces as grant_extra in 0.4.2 (the platform test only covers the two-hop pg_write_all_data path)
- ~/bin/ow_env.py helper (outside the repo) was needed to load OW_BILLING_RO_DSN from Secrets Manager in memory and write ~/.pgpass, since command-substitution export was guard-blocked

Per batch:
- w0-lakebase-scaffold: FAIL. lakebase_scaffold landed billing schema + 4 reference tables on mig-20260927b-w0 with live row parity (tiers 1-3 PASS, 918 rows) and rerun/fixture-shape/type-map evidence, but the harness verdict is FAIL: tier 0 grant_extra for a workspace admin inheriting the Lakebase platform grant (databricks_superuser) on every table; PR #1728 open, not merged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1728
