# 07_access_checklist.md — environment probes, D10 items, access model

Probed 2026-09-01 20:57–21:05 UTC from the setup session. Secrets referenced by name only.

## A. Probe results

| # | Probe | Result | Evidence |
|---|---|---|---|
| A1 | Databricks auth + serverless warehouse (`DATABRICKS_DEMO_HOST`/`DATABRICKS_DEMO_TOKEN`) | WORKS | `SELECT current_user()` SUCCEEDED; warehouse `565cd2fd713738c4` RUNNING, `enable_serverless_compute=true` |
| A2 | Target catalog `ow_tp` exists | BLOCKED (absent) | `SHOW CATALOGS` → banking_analytics, de_demo_workspace, migration_demo, redshift_src, ricky_kartolo, samples, system, tsql_demo. Preflight `make tp-preflight PLATFORM=databricks` → 3/10 DENIED (`files-get-directory`, `files-put-get`, `uc-create-list`: "Catalog 'ow_tp' does not exist"). Manifest `.tp-preflight/databricks-capabilities.json`. |
| A3 | Token can CREATE CATALOG | WORKS | `CREATE CATALOG IF NOT EXISTS ow_tp_preflight_probe` SUCCEEDED, `DROP CATALOG ... CASCADE` SUCCEEDED, `SHOW CATALOGS LIKE 'ow_tp*'` empty afterwards. (Metastore grants list `CREATE CATALOG` only for the workspace-admins group and `is_account_group_member` returned false, so the right is workspace-local; the direct probe is authoritative.) → D10-1 is parent-executable, no customer request needed. |
| A4 | Jobs / secret scopes / Files API scopes | WORKS | preflight `jobs-create-list`, `jobs-delete`, `secret-scope`, `secret-scope-delete` VERIFIED; Files probes will re-verify once `ow_tp` exists (token has `files` scope per credentials note). |
| A5 | Legacy runtime (`ksh`, `perl`, `awk`, `sshpass`, `docker`) | WORKS | all present; `ksh 93u+m/1.0.0-beta.2`; `docker ps` ok |
| A6 | Golden baseline regeneration NS=demo | WORKS | `make legacy-etl-gen-data NS=demo` + `make legacy-etl-run JOB=run_all` under `OTTERWORKS_LEGACY_ROOT=/home/ubuntu/otterworks-legacy-setupprobe`: 100 `.psv` rows, finance report equals the 6 documented rows exactly (EUR INVOICE 22 101554.41 … USD CREDIT 7 33390.44) |
| A7 | AWS auth (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`) | WORKS (region unset) | identity `arn:aws:iam::599083837640:user/Devin-PartnerWorkshops-Demo`; all `simulate-principal-policy` creates allowed; S3/IAM list ok. 12/26 probes DENIED solely with `NoRegion` — environment gap: `AWS_DEFAULT_REGION=us-east-1` must be exported before preflight/children run (D10-4). Leftover scan: 10 pre-existing `ow-tp-*` IAM roles from other demo tracks (informational, not ours). |
| A8 | Contract/recon validators | WORKS / expected FAIL | `make tp-validate-schemas` PASS; `make tp-validate-recon` PASS (0 files); `make tp-validate-contracts` FAIL "no JSON contract files found" — expected until wave 0 authors contracts (D10-2). |
| A9 | Smoke gate | WORKS | `make tp-smoke` → "all checks passed" in 12.6 s |
| A10 | `infrastructure/terraform-databricks/`, `scripts/tp_databricks/dbx.py` | BLOCKED (absent) | only `scripts/tp_databricks/local_fixture.py` exists; D10-2. |
| A11 | Production legacy host access | N/A | none exists or is requested; legacy = git tree + deterministic fixtures |

## B. D10 items and fired requests

| ID | Item | Status | Request / action |
|---|---|---|---|
| D10-1 | Create `ow_tp` catalog, schemas, volume, secret scope | OPEN → parent wave 0 | No customer action: token holds CREATE CATALOG (A3). Parent applies shared Terraform, then reruns preflight to a 10/10 manifest before any child launch. |
| D10-2 | Author `infrastructure/terraform-databricks/`, `dbx.py`, 9 unit contracts | OPEN → parent wave 0 | No customer action. |
| D10-3 | Legacy runtime prerequisites | CLOSED | A5/A6 WORKS. |
| D10-4 | AWS region not configured on the VM | OPEN → parent | Export `AWS_DEFAULT_REGION=us-east-1` in the run environment and child hand-offs; propose adding to the repo blueprint. No customer action. |
| D10-5 | Security reviewer + cutover-principal holder unnamed | OPEN → user | Asked at STOP A. |

No D10 item requires a customer lead time; the current access tier can execute wave 0 immediately after STOP A.

## C. Access model (for the security reviewer)

| Tier | Purpose | Principal | Rights | Used by |
|---|---|---|---|---|
| Assessment | inventory, lineage from source | git read of `tech-partnerships`; Databricks read (`SHOW`, `SELECT` on `ow_tp`, `system`) | metadata + read-only | setup, inventory, analysis, plan sessions |
| Migration | build and reconcile | `DATABRICKS_DEMO_TOKEN` (PAT; scopes sql, unity-catalog, jobs, secrets, workspace, files) + `AWS_ACCESS_KEY_ID` | write inside catalog `ow_tp` and `ow-tp-*` AWS resources only; no DDL on shared tables; no grants on other catalogs; no clusters; no Workflow left unpaused | parent (live window, wave 0) and children (fixture-mode only; Databricks writes limited to disjoint `ns` slices when unavoidable) |
| Cutover | re-point production consumers, retire cron lines | customer-held, never a Devin secret | production repoint | customer at STOP E only |

Attribution: every object carries `ns`; every write comes from a PR on the run branch; Databricks
`system.access.audit` and the job `run_as` identity (the PAT owner) record the session; AWS
resources carry `Project=otterworks-tp`. Legacy is never written to in any tier.
