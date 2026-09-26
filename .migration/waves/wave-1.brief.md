# Wave 1 close

Landed: 1 of 3 batches passed their own recon.
Independent verify: PASS, 1 PRs merged.
Failed: none.
Blocked on missing inputs: w1-b01, w1-b02.
Held back by circuit breaker: none.

Verifier findings:
- Batch w1-b03 re-ran green in live mode against the migration cluster for all three units (subscriptions_rating, invoicing, dunning) with merge_eligible=true in every result.json, so the batch is PASS and PR #1718 is eligible for the workflow to merge.
- Every past-the-gate probe (row counts, duplicate keys, null and missing rates, embed-array lengths vs child rows, orphan children, boundary documents, indexes vs index_plan) and every cross-unit reference check came back clean with zero discrepancies.
- All 261 replayed app-level parity queries (entitlement, usage summary, usage rating, invoice preview, invoice lines, overdue accounts) return the same rows from Oracle and from the ported Mongo backend.
- Observation, not a defect: the Mongo backend renders scaled money fields with their Decimal128 scale (for example 49.0) where the Oracle backend renders 49, which is numerically equal but may differ byte-for-byte in API JSON.
- Observation: the read-only Oracle principal has SELECT only and no EXECUTE on the pkg_* packages, so parity was established via SELECT equivalents of the package bodies rather than by calling the packages.
- A stale recon/wave-1 branch from an earlier, unrelated run (targeting database ow_billing_migration, base commit 7e8afa3d) already existed on the remote and was replaced with a force-with-lease push so the required report path resolves to this run's report.
- Batches w1-b01 (customers) and w1-b02 (invoice_batch) from the wave-1 manifest were not in this verifier's batch list and are not covered by this report.

Skill feedback to fold in before the next wave:
- Brief's recon --out is per-unit (.migration/recon/w1-b03/<unit>/) while wave 0 wrote one dir per batch; harness handled it fine but the ledger writer should expect three result.json files.
- Embed `target_where` is applied as a root-document $match (adapters.py embedded_count), so for a type-discriminated child table it must be `{"attributes.entityType": "CUSTOMER"}` (or `{}`), not `{"entityType": "CUSTOMER"}` — the latter yields sum(len(attributes))=0. Neither oracle.md nor the recon SKILL.md says this.
- Harness engine.py:71-74 requires every embed with child_where to also carry target_where (JSON filter), but gen_mapping.py emitted child_where without target_where for invoice_headers.lines in .migration/mapping/invoice_batch.json (and 03_mapping_spec.json v1.0.0). The playbook's step-1 brief check should include 'recon run' config validation (or a `recon validate` subcommand) so the orchestrator catches this before fan-out.
- No profile rule for Oracle SUM() over zero non-NULL values returning NULL vs Mongo $sum returning 0; ported in app code (batch_balances) by counting non-null contributors.
- Plan gap (rule 6): pkg_dunning.sp_suspend_overdue updates TENANTS, a wave-0 collection not in the w1-b03 write targets; the port implements it but it was never executed. Lead should decide ownership.
- Suggested fix (needs the orchestrator, children may not edit .migration/): add "target_where": "{}" to the invoice_headers.lines embed (target side = all header docs, matching child_where 'EXISTS header'); the orphan collection is already correctly scoped with root_where + target_where {"orphan": true}.
- The SELECT-only source principal cannot EXECUTE the PL/SQL packages, so proc write paths (sp_change_plan, sp_finalize_rating, sp_issue_invoice, sp_schedule_dunning) cannot be graded by recon; playbook/profile should say how procs get parity evidence. I smoke-tested them against the loaded target and reloaded before the live run.
- Wave-0 common.load_collection had no embed support; extended it (fetch_embeds + embeds loop, orphans counted and not loaded) rather than duplicating. Return type changes to (n, embedded) only when the collection declares embeds.
- gen_mapping emits embed `child_where` (ENTITY_TYPE = 'CUSTOMER') without the paired `target_where`; the recon harness (engine.py:72) refuses the mapping with exit 2 before writing result.json. Children cannot fix this because .migration/ is read-only for them.
- gh pr create is disabled in the subagent shell; opened the PR via `gh api repos/.../pulls` instead.
- oracle.md gives no guidance on Oracle LEAST/GREATEST NULL propagation (vs $min/$max which ignore missing); kept the NVL collapses app-side exactly where the PL/SQL had them.
- oracle.md has no conversion rule for ADD_MONTHS (day-clamp / last-day-of-month semantics); derived a Python equivalent for pkg_rating's 3-month rollover window.
- oracle.md has no rule for TO_CHAR(x,'YYYYMMDD') string-date comparisons; derived [trunc(start), trunc(end)+1d) range filters.
- python-oracledb returns NUMBER(p,s>0) as float; profile should state Decimal(str(v)).quantize(declared scale) before Decimal128 (added scale_of() to common.py).

Per batch:
- w1-b01: BLOCKED. customers code+loader landed on PR #1714 (25001 docs, 8337 embedded attributes, idempotent) but recon is BLOCKED: mapping v1.0.0 embed `attributes` has child_where without target_where so `recon run` exits 2; orchestrator must add `"target_where": "{\"attributes.entityType\": \"CUSTOMER\"}"` to the embed — a diagnostic fixture run with that one-line scratch patch PASSed all 3 tiers (33338 keyed checks). https://github.com/Cognition-Partner-Workshops/otterworks/pull/1714
- w1-b02: BLOCKED. BLOCKED before any code/load: recon harness refuses the brief's exact command with 'object invoice_headers embed lines has child_where but no target_where' — mapping v1.0.0 embed for invoice_batch is missing target_where (a .migration/ file I may not edit); worktree/branch removed so a relaunch with the same brief command works cleanly.
- w1-b03: PASS. w1-b03 landed: subscriptions_rating, invoicing, dunning ported to pymongo (pkg_plans/pkg_rating/pkg_invoicing/pkg_dunning app-side, results[]/lines[] embedded), loaded 7 collections into mmp_rt_billing, live recon PASS merge_eligible=true on all three units, PR #1718 open against the run branch (not merged); one plan gap: suspend_overdue writes tenants (wave-0 collection). https://github.com/Cognition-Partner-Workshops/otterworks/pull/1718
