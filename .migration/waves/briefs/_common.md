RUN CONTRACT (read .migration/00_context.md, 01_conventions.md, 03_recon_tolerances.*, allowed_targets.json first).
- Run 20260927; base branch tp-run/databricks-20260927T122304Z; open exactly one PR from a branch
  mig/20260927/<batch_id> into tp-run/databricks-20260927T122304Z; never merge it. Never touch main or
  tech-partnerships.
- Oracle OW_BILLING (52.201.36.9:1521/FREEPDB1) is READ-ONLY. The DSN is the env var OW_BILLING_RO_DSN
  (helper: source /home/ubuntu/bin/ow_oracle_env.sh, secret ow-tp/oracle/ow_billing_ro, principal OW_BILLING_RO).
  Never print it. Fixture first (services/legacy-billing fixtures, testdata/legacy oracle_billing_seed NS=demo),
  then ONE live read per stage.
- Databricks: service principal d9d1c4ec-29da-4ec7-9aa0-e932710d61e2, DATABRICKS_AUTH_TYPE=oauth-m2m, no PAT,
  catalog ow_tp, warehouse 565cd2fd713738c4. Write only to your declared write_targets; any other write halts the
  wave. Schedules PAUSED. No cutover, no BILLING_BACKEND change on any deployed service, never Lakebase branch
  `production`, never ow_tp.bronze / ow_tp.silver / ow_tp.gold / airbyte / fivetran schemas.
- Lakebase: project ow-tp-billing, database ow_tp, branch mig-20260927-w0, host
  ep-wild-hat-d120fhwn.database.us-west-2.cloud.databricks.com (helpers /home/ubuntu/bin/ow_lakebase_env.sh and
  ow_lakebase_pgpass.sh; psql with the literal host and an env-var DSN only). Objects are owned by the service
  principal role.
- Recon: ~/.venvs/dbx-recon/bin/dbx-recon --family oracle from the session bridge (never from serverless), mapping
  .migration/units/<unit_id>/mapping_spec.json, tolerances .migration/03_recon_tolerances.json (tol-20260927-v1),
  params --param ns=demo --param batch_no=85559852 --param admin_tenant_id=a0000000-0000-0000-0000-000000000001
  --param fixture_tenant_id=00000000-0000-0000-0000-000000000001. Reports go under .migration/recon/<unit_id>/,
  the ONLY .migration path you may write. Max 3 full recon attempts, then stop and report. Only a dbx-recon
  verdict is parity; fix recon failures in converted code, never in the source or the tolerances.
- Before the PR: make tp-smoke, the tp-pre-pr-self-check skill for your unit, lint/typecheck/affected tests for
  code you touch. Report: changed paths, write targets actually written, recon verdict + report paths, PR URL.
- Secrets by name only. Do not edit .migration/05_progress.md, allowed_targets.json, 06_decisions.md, waves/.
