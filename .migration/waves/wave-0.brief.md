# Wave 0 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w0-lakebase-scaffold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 4, 'tier2': 4, 'tier3': 12, 'tier4': 0, 'total': 20}, target_statements={'tier1': 4, 'tier2': 4, 'tier3': 8, 'tier4': 0, 'total': 16}, source_rows_fetched=926, target_rows_fetched=926; actual source_statements=53, target_statements=38, source_rows_fetched=918, target_rows_fetched=918, harness time 5s. Verifier depth full, overrides: w0-lakebase-scaffold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- Lakebase adapter needs bare object names + --target-catalog/--target-schema; a mapping spec with ow_tp.billing.<t> fails 'invalid SQL identifier' — had to derive a de-qualified copy under the unit recon dir
- fixture-shape --source-statement-cap: the contract gives no number; 20 was too low (19 profiled columns + 4 shape reads), needed a second live pass at 40
- live-read count: load stage ran twice (rerun proof required a fresh drop/apply after the trigger removal) and fixture-shape twice (cap), beyond 'one live read per stage'
- load_reference.py cannot be run as a module from the repo root (databricks/ is not a package); run with PYTHONPATH=<dir>
- local Oracle fixture carries TRG_USAGE_EVENTS_CHECK that the live OW_BILLING dictionary does not; fixture recon and live recon disagree on triggers
- rerun proof: a first-run scaffold has no prior committed shape, so the evolved leg is always 'unsupported' and rerun_unsupported blocks merge; wave-0 needs a declared prior shape or an exemption
- routine_parity_missing fires without a dependencies.json even for a unit with no routines; had to commit an empty one under .migration/recon/<unit>/ (units/ is protected)
- structure.compare_grants flags Lakebase's platform-inherited grants (databricks_superuser -> pg_write_all_data -> workspace admin) as grant_extra; no rule/principal_map form can express 'platform role, not unit-granted', so every Lakebase table fails tier 0

Per batch:
- w0-lakebase-scaffold: FAIL. billing schema + 4 reference tables landed on mig-20260927-w0 with live row parity PASS (918 rows), but recon FAIL/not merge-eligible: Lakebase platform-inherited grants (databricks_superuser -> workspace admin) flagged grant_extra on every table and rerun proof is unsupported without a prior shape; PR #1727 open, unmerged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1727
