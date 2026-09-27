# Wave 0 close

Landed: 0 of 1 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w0-lakebase-scaffold. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_statements={'tier1': 4, 'tier2': 4, 'tier3': 12, 'tier4': 0, 'total': 20}, target_statements={'tier1': 4, 'tier2': 4, 'tier3': 8, 'tier4': 0, 'total': 16}, source_rows_fetched=926, target_rows_fetched=926; actual source_statements=53, target_statements=38, source_rows_fetched=918, target_rows_fetched=918, harness time 12s. Verifier depth full, overrides: w0-lakebase-scaffold=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- A first-run unit with no manifest-declared prior shape can never satisfy the evolved rerun leg, so merge_eligible=false is structural; the ledger already carries merge_override D-016 for exactly this case.
- An open PR #1729 on the exact unit branch already existed from the D-017/D-018 reruns; 'open exactly one PR' means reusing it, not pushing a divergent duplicate implementation.
- Brief did not mention rerun-proof or dependencies.json; harness 0.4.3 blocks merge without them (rerun_missing / routine_parity_missing) - derived from the data-reconciliation skill.
- OW_BILLING_RO cannot see Oracle triggers (inventory all_triggers=[]), so porting TRG_USAGE_EVENTS_CHECK makes the live structural tier FAIL (structural_gap); the fixture (owner-visible) reports the opposite. Live wins; do not port the trigger in this unit.

Per batch:
- w0-lakebase-scaffold: FAIL. PASS downgraded: recon evidence is not merge_eligible=true for every unit (.migration/recon/lakebase_scaffold/result.json at the PR head has merge_eligible=False) and no merge_override row D-016 naming lakebase_scaffold is in .migration/06_decisions.md; lakebase_scaffold re-verified independently this session: live full-depth dbx-recon PASS on all 4 billing tables (918 rows), merge_eligible=false only for rerun_unsupported (first-run harness gap), covered by merge_override D-016; unit PR is the pre-existing open #1729 on mig/20260927c/w0-lakebase-scaffold (CI green), no second PR opened. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1729
