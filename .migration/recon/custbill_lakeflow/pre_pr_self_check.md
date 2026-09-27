# tp-pre-pr-self-check — custbill_lakeflow (run 20260927c)

| Item | Status | Evidence |
|---|---|---|
| NULL/missing attribution cannot fail open | PASS — 5 expect_or_drop expectations on silver MV; rejects land in `mig_20260927c_quarantine.custbill_rejects` with reject_reasons (fixture proof: 1 row, 4 reasons) | pipeline_events_fixture.json, quarantine_fixture.json |
| All references scoped to unit namespace `ow_tp.mig_20260927c_*` / `ow_tp_20260927c_*` | PASS — bronze/silver/quarantine tables, volumes custbill_landing + custbill_out, pipeline + job names verified via `pipelines get` / `jobs get` | structural.json |
| No DDL drops/replaces/alters on shared tables | PASS — only unit tables dropped+recreated by pipeline (bronze x4); render uses CREATE OR REPLACE on its own one-row manifest table | live updates |
| Retention/cleanup safe on rerun | PASS — pipeline re-run idempotent (ran 5 updates; MVs recompute, quarantine cleared to 0 on final run) | live_counts.json |
| Cleanup retains run evidence | PASS — no cleanup; all artifacts under `.migration/recon/custbill_lakeflow/` | this dir |
| No secrets/tokens/real emails in source or evidence | PASS — DSN only via OW_BILLING_RO_DSN env, never printed/persisted | files |
| Parity-vs-tolerance per contract | PASS — file contract byte-for-byte (D7): sha256 equality proven | custbill_sha256.json |
| Idempotency proven by actual rerun | PASS — 5 pipeline updates run (incl. 2 --full-refresh), final counts stable | pipeline_events_*.json |
| Recon values recomputed from target | PASS — counts/sha queried via SQL warehouse 565cd2fd713738c4 | live_counts.json, render_manifest.json |
| Unverified paths listed | rerun-proof not produced (see recon result.json merge_block_reasons) | result.json |
| `"kind": "recon-report"` / `*.recon.json` | dbx-recon result.json carries the schema | .migration/recon/custbill_lakeflow/ |
| Capability preflight | oracle live read executed once (landing) + once (legacy .dat); Databricks writes all inside allowlist | landing_manifest.json, custbill_sha256.json |
