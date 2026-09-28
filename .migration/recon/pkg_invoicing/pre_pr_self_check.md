# Pre-PR self-check — pkg_invoicing (run 20260927c, wave w1-lakebase-packages)

- [x] NULL/missing attribution cannot fail open — true: routines use Oracle NVL semantics; loader verifies extract trailer counts before commit (load_state.py).
- [x] All references scoped to ow_tp / ow-tp- namespace — true: all objects under ow_tp.billing; load_state.py enforces current_database()='ow_tp'.
- [x] No DDL drops/alters a shared table — true: 10_billing_state.sql drops only the 8 unit-owned state tables + 2 unit sequences.
- [x] Retention/cleanup safe on rerun — true: job_purge_audit_log retention mirrors Oracle (purge before cutoff, keeps newer rows).
- [x] Cleanup retains run evidence and recon artifacts — true: .migration/recon/pkg_invoicing/ committed.
- [x] No secrets in source/evidence — true: git grep 'oracle://|password|pgpass' over databricks/mig_20260927c + .migration/recon yields only secret-NAME references and parser regex.
- [x] Parity-vs-tolerance decision per contract — true: tol-20260927c-v1 untouched; git diff origin/tp-run/databricks-20260927T194945Z -- .migration/03_recon_tolerances.json is empty.
- [x] Idempotency proven by actual rerun — true: .migration/recon/pkg_invoicing/rerun_proof.json fresh leg=pass + exec extract/load rerun reproduced fixture invoice 109bb68d.
- [x] Recon recomputed from target — true: result.json mode=live (recon attempt 2 on Lakebase w0).
- [x] Unverified/untested paths listed — true: evolved rerun leg unsupported (pre_shape == fresh shape; identity invisible to shape); Oracle source trigger dictionary invisible to RO principal (pkg_plans trigger_extra, see structural.txt).
- [ ] Recon report declares "kind": "recon-report" — false: result.json contains nested "kind": "harness" only; no top-level recon-report kind (harness result schema, not the machine-readable report schema).
- [x] Capability preflight passed — true: .migration/09_capabilities.json ready=true.
- [x] make tp-smoke green — true: 6 passed, output in .migration/recon/pkg_ow_util/tp_smoke.txt.
