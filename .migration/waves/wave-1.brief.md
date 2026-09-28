# Wave 1 close

Landed: 0 of 2 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w1-custbill-lakeflow, w1-lakebase-packages. Blocked: none. Held by circuit breaker: none.
Cost: estimated source_rows_fetched=202228, target_rows_fetched=202228; actual n/a, harness time 496s. Verifier depth full, overrides: w1-custbill-lakeflow=sampled, w1-lakebase-packages=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- Oracle ALL_TRIGGERS returns nothing for OW_BILLING_RO; doctor recorded trigger_census {} as ok, so tier-0 trigger_extra on every trigger-bearing target is unavoidable until a dictionary grant or a ledger rule exists
- brief: dependencies.json (zero routines) must be committed and passed via --routine-dependencies before the merge-evidence run, otherwise routine_parity_missing blocks; the brief did not say so for a table-only unit.
- data-reconciliation harness: recon.adapters._databricks_connect passes oauth_client_id/oauth_client_secret to databricks-sql-connector 4.6.0, which has no M2M client-secret kwarg and falls into the U2M browser-OAuth wait; both live stalls (attempt 1 35 min, attempt 2 10 min) were this. Workaround: mint the SP access token in-process via databricks.sdk Config().authenticate() and hand it to the harness' access_token path.
- data-reconciliation: an SDP unit can never clear rerun_missing, so merge_eligible is structurally false for Lakeflow units; the harness needs a not_applicable rerun posture or the brief a standing merge_override.
- dbx-recon run --rerun-proof also requires --rerun-source <DDL file>; not in the brief
- factory-doctor: probe ow_tp.information_schema.table_privileges readability for the SP; its ServerOperationError surfaces only as structural_gap after a 8-minute live run.
- git: the branch had to be merged forward from the base (D-007(6)); a rebase made the push non-fast-forward and was rebuilt as a merge + cherry-pick.
- harness Postgres reader grades an OWNED BY sequence as identity; brief says 'plain sequence' but must also say 'not OWNED BY the column'
- predecessor's ledger commits were replayed onto the unit branch with new shas; merge the base forward (D-007) or the PR diff shows .migration/waves
- rerun-proof evolved leg is unsupported whenever the prior committed DDL differs only in identity/default (shape = name/type/nullable); packages brief should say how first-run units get an evolved leg
- the guard rejects $var in a dbx-recon --unit loop; unit names must be literal per command

Per batch:
- w1-custbill-lakeflow: FAIL. custbill_lakeflow: live sampled dbx-recon PASS on all 4 bronze tables (152k keyed rows), .dat sha256 byte-identical, all 4 gates have evidence on PR #1731, but result.json merge_eligible=false (rerun_missing for an SDP, routine_parity_missing, table_privileges structural_gap) so status FAIL/missing_rule pending a human merge_override. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1731
- w1-lakebase-packages: FAIL. Packages converted, deployed to w0+exec, routine parity 44/44 and Tenant One invoice identical; live recon PASS on pkg_ow_util/pkg_rating/pkg_invoicing, pkg_plans FAIL only on trigger_extra (ALL_TRIGGERS invisible to RO principal), all four merge_eligible=false on rerun_unsupported (shape gap, cf. D-016); attempts used 2/3. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1730
