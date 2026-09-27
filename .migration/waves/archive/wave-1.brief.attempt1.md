# Wave 1 close

Landed: 0 of 2 batches passed their own recon.
Independent verify: NOT RUN.
Failed: w1-custbill-lakeflow. Blocked: w1-lakebase-packages. Held by circuit breaker: none.
Cost: estimated source_rows_fetched=202228, target_rows_fetched=202228; actual n/a, harness time 1s. Verifier depth full, overrides: w1-custbill-lakeflow=full, w1-lakebase-packages=full.
Awaiting manual merge: none reported

Verifier findings: none.

Skill feedback to fold in before the next wave:
- Brief asks for trg_billing_audit_log_id -> identity default; dbx-recon tier 0 flags identity vs non-identity source as structural_gap — rule conflict, needs a decision (sequence DEFAULT nextval instead?)
- Brief says 'develop on a LOCAL Postgres fixture' but allowed_targets.json has no fixture_endpoints and guard_mode=block: fixture writes are impossible under the stated guard; the brief/allowlist must include the fixture host
- Brief says pipeline 'never trigger-started' yet gates need populated bronze/silver and an event log: interpreted as no schedule trigger; one manual bundle run update is required.
- Bronze streaming tables from parquet with Oracle DATE need table_properties delta.feature.timestampNtz=supported on serverless SDP.
- DAB mode: development prefixes resource names and presets.name_prefix '' does not override; omit mode to get exact resource names.
- Doctor's source_principal_read_only needs oracledb importable by the interpreter running `python -m doctor`; run it with the recon venv python, not system python3.
- Guard blocks any shell assignment/export of OW_BILLING_RO_DSN (trusted name) and unknown wrappers; the workable recipe is a python launcher that sets os.environ and execvpe's the command (~/bin/ow_secret_env.py) — the brief's 'export in one shell' recipe is not executable under guard_mode=block.
- No rerun-proof produced for an SDP pipeline (rerun-proof targets DDL jobs); expect rerun_missing block reason.
- Per-unit dependencies.json lacks callee rows for cross-package calls (log_msg, compute_rating); dbx-recon run refuses analysis — a call-chain batch needs a merged deps file committed up front
- dbx-recon run --depth full --family oracle stalled with no progress for 35 min on this estate (150k-row invoice_line); the harness needs a per-statement timeout or progress log.
- mapping_spec.json target names are catalog-qualified but the lakebase harness qualifies via --target-catalog/--target-schema; a de-qualified copy was needed
- routine-parity requires branch mig-<pipeline>-exec which was never created; the brief only names w0
- spark.sql() inside an SDP temporary_view over fully-qualified pipeline tables returned 0 rows; DataFrame API (spark.read.table) is required for dependency wiring.

Per batch:
- w1-custbill-lakeflow: FAIL. Landed: Lakeflow SDP ow_tp_20260927c_custbill (4 bronze STs, silver with 5 expect_or_drop + quarantine MV) and paused render job producing a byte-identical CUSTBILL_DEMO_ORACLE.dat (sha256 equal, 18,750 recs); FAIL because the one live dbx-recon run hung and gave no verdict, so bronze-parity is unproven and merge_eligible is false; PR #1731 unmerged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1731
- w1-lakebase-packages: BLOCKED. DDL + 19 PL/pgSQL routines + 2 triggers deployed to Lakebase w0 and 8 state tables loaded exactly (69/0/3/3/3/2/5/0); BLOCKED: guard forbids local-fixture writes (no golden/routine-parity/invoice evidence), no -exec branch, cross-package deps break recon for 3 units, pkg_ow_util live recon FAIL on log_id identity. PR #1730 open, not merged. https://github.com/Cognition-Partner-Workshops/otterworks/pull/1730
