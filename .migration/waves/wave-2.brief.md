# Wave 2 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w2-finance-close-gold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 1, 'tier2': 1, 'tier3': 3, 'tier4': 0, 'total': 5}, target_statements={'tier1': 1, 'tier2': 1, 'tier3': 2, 'tier4': 0, 'total': 4}, source_rows_fetched=18750, target_rows_fetched=18750; actual source_statements=14, target_statements=9, source_rows_fetched=18750, target_rows_fetched=18750, harness time 23s. Verifier depth full, overrides: w2-finance-close-gold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- Guard rejects inline VAR=... env assignments and $(...) substitution; the DSN/token export recipe in the brief cannot be typed as written, needed an out-of-repo python exec helper.
- Harness mapping object must be the bare table name when --target-catalog/--target-schema are passed; the unit mapping_spec is fully qualified, so a dequalified copy under .migration/recon/<unit>/ was needed.
- OW_BILLING_RO principal has no synonyms: the repo Oracle extractor needs CURRENT_SCHEMA=OW_BILLING; brief should say so (used a runtime-only wrapper, source untouched).
- The doctor rewrites .migration/09_capabilities.json; children must git checkout it before committing or the ledger-tamper rule trips.
- databricks lakeview create/get are not guard-allowlisted; dashboards must go through DAB resources.dashboards with per-dataset catalog/schema, not --dataset-catalog/--dataset-schema.
- make tp-smoke runs from the repo Makefile; brief could name it as the smoke gate command (~2 min, uv sync).
- rerun-proof evolved leg is always 'unsupported' on a first-run unit (no prior committed shape); merge_eligible can never be true on wave-first units without a decision row.
- result.json does not persist Tier-2 aggregate values on PASS; the brief's 'print aggregate_sum(TOTAL_AMT)' requires re-reading via recon.adapters sum_probe.

Per batch:
- w2-finance-close-gold: FAIL. PASS downgraded: recon evidence is not merge_eligible=true for every unit (.migration/recon/finance_close_gold/result.json at the PR head has merge_eligible=False) and no merge_override row D-<n> naming finance_close_gold is in .migration/06_decisions.md; finance_close_gold landed: gold finance_close_detail/finance_close (18750 rows, 187618458.58 = legacy = SUM(detail) = Tier-2 sum), paused job run twice, dashboard published; live recon PASS x2 but harness merge_eligible=false (table_privileges structural_gap, rerun evolved leg unsupported on first run); PR #1732 open, not merged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1732
