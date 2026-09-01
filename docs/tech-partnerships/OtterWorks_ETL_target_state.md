# OtterWorks ETL box → Databricks lakehouse: target state

Version 1.0-draft (2026-09-01), authored by `!dbx_migration_setup` Phase 1 on run branch
`tp-run/databricks-20260901T205308Z`. Every field is **FACT** (cited) or **PROPOSED**
(default awaiting STOP A). Out-of-scope surfaces are marked N/A with a reason.

Sources consulted (all on this repo):
- S1 `docs/tech-partnerships/contracts/README.md` — shared target rules (catalog, prefix, compute, `ns`, PR gate).
- S2 `docs/tech-partnerships/contracts/schema/unit-contract.schema.json`, `recon-report.schema.json` — machine-readable acceptance and evidence shapes.
- S3 `docs/tech-partnerships/runbook-databricks.md` — medallion mapping for the CUSTBILL chain, recon contract, deterministic NS=demo baselines.
- S4 `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md` §Deficiency inventory; `etl/ETL_UPGRADE_GUIDE.md` §Migration Axes, §Script-to-DAG Mapping — acceptance checklists per unit.
- S5 `.migration/00_context.md`, `.migration/00_intake_template.md` — intake facts.
- S6 Kit skills (plugin `dbx-migration`): `unity-catalog-conventions`, `dlt-pipelines`, `asset-bundles`, `data-reconciliation`, `databricks-auth-cli`, `backfill-planner`.
- S7 Knowledge notes: branch topology & reproducibility policy; credentials map & platform limits.
- S8 `scripts/tp_databricks/local_fixture.py`, `scripts/tp_preflight/databricks.py` — fixture layer and capability preflight.

No reference implementation exists on the run branch or on `tech-partnerships` (S1 lists nine
contract files and `infrastructure/terraform-databricks/`; none are present — D10-2). Where a
convention below is PROPOSED it is because the only evidence is prose, not merged code.

---

## CORE (applies to every unit)

| Field | Value | Tag / cite |
|---|---|---|
| Unity Catalog layout | catalog `ow_tp`; schemas `bronze`, `silver`, `gold`; managed volume `/Volumes/ow_tp/bronze/landing`; volume paths `<ns>/<unit>/...`; every table carries an `ns` column; every job takes an `ns` parameter (`demo` this run) | FACT S1 L15-28 |
| Environments | one shared demo workspace (`DATABRICKS_DEMO_HOST`); environment isolation is by `ns`, not by catalog or workspace | FACT S7 |
| Table naming | `ow_tp.<layer>.<unit_or_entity>[_<qualifier>]`, snake_case; quarantine tables `ow_tp.silver.<entity>_quarantine`; per-unit recon views (if any) `ow_tp.gold.recon_<unit>` | PROPOSED (S1 prefix rule + `unity-catalog-conventions`) |
| Object prefix | `ow_tp` on everything: jobs `ow_tp_<unit>`, secret scope `ow_tp`, notebooks `/Shared/ow_tp/<unit>/...`, DLT pipelines `ow_tp_<unit>`; never read/write/delete an unprefixed object | FACT S1 L23-26, S7 |
| Compute | existing serverless SQL warehouse `Serverless Starter Warehouse` (`565cd2fd713738c4`) and serverless notebook/job tasks only; never create clusters or anything with an hourly cost | FACT S1 L25-26, S5 |
| Delta conventions | Delta only; no partitioning at this scale (≤10^4 rows/ns); liquid clustering optional on `ns`; `ns` is always the first filter; column names snake_case; typed columns (DECIMAL(18,2) money, DATE dates, STRING codes) | PROPOSED |
| Shared-table DDL | **Never** `DROP`/`CREATE OR REPLACE` a table that another namespace or unit may read; additive `ALTER TABLE ADD COLUMNS` only, parent-approved; children create only tables they own (named in their contract `target_objects`) | FACT S7 (column loss incident) |
| Code language policy | PySpark/Python notebooks for ingest, parsing and non-tabular I/O (S3, SQS, DynamoDB, REST); Spark SQL for silver→gold aggregates; DLT (SQL or Python) where expectations are the quality gate; no Scala, no shell | PROPOSED (`dlt-pipelines`) |
| Repo layout | code under `databricks/<unit>/` (notebooks/source, tests, `recon_<unit>.py`); Terraform job definitions `infrastructure/terraform-databricks/jobs_<unit>.tf`; contracts `docs/tech-partnerships/contracts/<unit>.md` + `<unit>.contract.json`; recon evidence `docs/tech-partnerships/recon/<unit>.recon.json` | PROPOSED (S1 L20-22 fixes the `jobs_<unit>.tf` path; rest defaulted) |
| Deployment mechanism | Terraform (`infrastructure/terraform-databricks/`, parent applies shared stack; children contribute `jobs_<unit>.tf` only and never run `apply`/`destroy`); notebooks deployed via `scripts/tp_databricks/dbx.py` (to be authored in wave 0, D10-2); Asset Bundles not used this run | FACT S1 L19-31 for the rule; PROPOSED that DAB is out |
| CI gates | every PR: `make tp-smoke` (golden path), `make tp-validate-contracts`, `make tp-validate-recon FILE=<report>`; pre-PR: `.agents/skills/tp-pre-pr-self-check`; unit tests under `databricks/<unit>/tests` runnable with plain `pytest` (no Spark cluster) | FACT S1 L37, S7; PROPOSED test location |
| Test conventions | pure-Python parsing/aggregation logic factored out of notebooks so it is unit-testable against the fixture layer (`make tp-fixture-land NS=<ns>`); byte-exact assertions where the legacy artifact is a file | PROPOSED (S8) |
| Secrets | Databricks secret scope `ow_tp` by name; AWS creds injected as secrets, never in code, notebooks, Terraform or PR bodies; `etl/config.ini` values are compromised-by-design and never copied | FACT S1, S5 §7, kit guardrails |
| Service principal | none available; the shared PAT (`DATABRICKS_DEMO_TOKEN`) acts for every session; activity attribution is by `ns` + run branch + PR | FACT S7 |
| Forbidden patterns | editing `etl/**`; touching `main`/`tech-partnerships`; clusters; unprefixed objects; DDL on shared tables; hostname branching; `2>/dev/null \|\| true`-style suppression; sleep-based dependencies; plaintext credentials; synthesized golden outputs; recon compared against self | FACT S1 L32-43, S3, S4 |
| Legacy is read-only | `etl/**` and the crontab are never modified; conversions fix themselves | FACT kit guardrail, S1 L35 |
| Unit = | one legacy script + its cron line(s) + the `run.sh`/`config.ini` slice it reads; one PR per unit into the run branch (org policy overrides S1's 3-PR stack) | FACT S5 §4, S7 |

### Drift rules (CORE): a PR is rejected if it
1. touches `etl/**`, `services/**`, compose files or CI, or targets any branch other than the run branch;
2. creates any object without the `ow_tp` prefix, or a cluster/instance pool/anything hourly;
3. runs `terraform apply|destroy`, or drops/replaces a table it does not own;
4. lacks a schema-valid `<unit>.contract.json` and a schema-valid `<unit>.recon.json` with `run_mode` set honestly;
5. embeds a credential value, or reads `etl/config.ini` at runtime;
6. hardcodes `ns=demo` (must be a parameter) or omits the `ns` column on a table it creates;
7. compares recon against numbers copied from a document instead of a regenerated legacy baseline.

---

## PIPELINE profile (the dominant surface: all 9 units)

| Field | Value | Tag / cite |
|---|---|---|
| Target runtime | Databricks **Jobs** with serverless notebook tasks as the default; **DLT** for the CUSTBILL silver layer where expectations implement quarantine; plain SQL warehouse tasks for gold aggregates | PROPOSED (S3 Beat 2, `dlt-pipelines`) |
| Medallion layering | bronze = raw landed bytes/rows as received (+ `ns`, `source_file`, `ingested_at`); silver = typed, validated, deduplicated rows with quarantine sibling; gold = business aggregates/reports consumed downstream | FACT S3 Beat 2 (CUSTBILL); PROPOSED extension to Python jobs |
| Incremental vs full | per-file incremental (Auto Loader / file-list manifest) for ingest; idempotent `MERGE` on natural key for silver; gold recomputed per `ns` per run (`INSERT OVERWRITE ... WHERE ns=?`) | PROPOSED |
| Reject-row handling | invalid dates, bad implied decimals, trailer/record-count mismatch, extra delimited fields → `ow_tp.silver.<entity>_quarantine` with `reason`, `source_file`, `raw_record`; never silently pass; zero quarantine on the clean NS=demo seed | FACT S3 Beat 4 / S4 deficiency rows; population rule PROPOSED |
| Restart / idempotency | every job re-runnable for the same `ns` with byte-identical outputs and unchanged row counts; proven by the mandatory `idempotency_rerun` in the recon report | FACT S2 recon schema |
| Mutual exclusion | Jobs `max_concurrent_runs=1`; no lock files | FACT S3, S4 |
| Parameterization | job parameters `ns` (required), `run_date` (optional, defaults to fixed clock for recon), no hostname/env branching | PROPOSED (S4 row 1) |
| Logging / errors | structured logging via `logging` to task output; all exceptions surfaced (no bare `except`/`|| true`); task retries 2 with alert on final failure | PROPOSED (S4 rows 6, 9; guide axis 6-9) |
| Legacy shape → target shape | ksh SFTP poll → landing volume + Auto Loader (S3 Transfer Family stands in for the mainframe drop, D7-1); fixed-width bash parser → silver DLT with expectations; Perl report → gold table + CSV/XLSX export task; `run_all.sh`+crontab → one Workflow DAG; Python jobs → Jobs per S4 Script-to-DAG mapping with Airflow tasks mapped 1:1 onto job tasks | FACT S3 Beat 2-3, S4 mapping; PROPOSED for Python detail |
| External systems of the Python jobs | SQS/DynamoDB/S3/Postgres/MeiliSearch/REST are reached from serverless tasks with credentials from scope `ow_tp`; in fixture mode they are LocalStack/compose; no new AWS resources beyond `ow-tp-` prefixed, serverless, tagged `Project=otterworks-tp` | FACT S7; PROPOSED fixture stance |
| Retention | bronze landing retained per `ns` for the run; `archive/`-forever behaviour replaced by Delta time travel + volume lifecycle documented per unit | PROPOSED (S4 retention row) |

### Drift rules (PIPELINE)
- Quarantine table missing where the contract lists a `must-detect` anomaly; or anomalies "detected" by filtering them out silently.
- `sleep`, polling loops, or wall-clock dependencies between tasks.
- A job that is not re-runnable for the same `ns` without duplicating rows.
- Any `run_mode: fixture` report presented as live proof.

---

## ORCHESTRATION profile

| Field | Value | Tag / cite |
|---|---|---|
| Scheduler target | Databricks Workflows replaces system cron; cron lines retired at cutover, not before | FACT S5 §6 D5 |
| Dependency model | one estate Workflow `ow_tp_estate_daily` (ingest → parse → finance) with task dependencies; Python jobs as their own Workflows; `run_all.sh` becomes the Sunday full-estate run of the same DAG (no separate code) | PROPOSED (S3 Beat 3 `dbx-orchestrate`) |
| Schedules | mirror legacy cadence (15-min ingest/parse, 02:00 analytics, 02:10→after-analytics finance, weekly jobs Sunday) as Workflow cron with `pause_status=PAUSED` during the run; nothing runs on a schedule until STOP E | FACT S7 (nothing runs on a schedule); PROPOSED cadence |
| Completion signalling | task-level dependency inside the Workflow; cross-Workflow via Delta table state (`ow_tp.gold.job_runs`) not files | PROPOSED |
| Alerting | job-failure email notification to a managed list defined as a Terraform variable (default: requester); no PagerDuty | PROPOSED |
| Backfill | `run_date` parameter re-run; history generator `make legacy-etl-gen-history` available but out of scope this run | FACT S5 §5 |

Drift: any Workflow left unpaused before STOP E; any dependency expressed as time offset.

## CONSUMER profile

| Field | Value | Tag / cite |
|---|---|---|
| Finance `.xls` distribution (D4-1) | gold table `ow_tp.gold.finance_billing` + exported CSV **and** real `.xlsx` to volume `reports/<ns>/`; delivery = Workflow email notification with link, recipients managed in Terraform var; `jake@` removed | PROPOSED |
| admin-service `activity_report.json` (D4-2) | keep S3 path and JSON shape byte-compatible (re-point nothing in admin-service this run) | PROPOSED |
| MeiliSearch index (D3-1) | remains the sink; the reindex Job writes it from the lakehouse-side silver copy of documents/files; no BI dashboards in scope | PROPOSED |
| Glacier archive | S3 Glacier object contract (JSONL.gz, key layout) preserved byte-for-byte | PROPOSED |
| SLA for consumer cutover | consumers re-pointed only at STOP E by the customer-held principal | FACT kit guardrail |

## SQL profile
N/A — no views, procedures or report SQL exist in the estate (the only SQL is inline `psycopg2` aggregates inside `analytics_daily.py` / `user_activity_daily.py`, handled under PIPELINE). Reason: FACT S5 §3.

## ML-SCORING profile
N/A — no model training or scoring jobs in the estate. Reason: FACT S5 §4 ("no BI/ML surface").

## DATA / DEPENDENCY profile

| Field | Value | Tag / cite |
|---|---|---|
| Coexistence mechanism | **dual-run**: legacy chain re-executed from the deterministic seed per `ns` (local, `OTTERWORKS_LEGACY_ROOT`) vs lakehouse outputs; no Lakehouse Federation (no legacy database engine) | PROPOSED S5 intake §3 |
| Dual-write | none; legacy keeps running on cron until STOP E | PROPOSED |
| Data target per legacy store | files (SFTP drop, `.psv`, reports) → volume + Delta; DynamoDB/SQS events → bronze Delta via boto3 tasks; Postgres aggregates → silver/gold Delta, Postgres still written for admin-service until STOP E; MeiliSearch → unchanged sink | PROPOSED |
| PII / masking | synthetic names only in fixtures; no masking rules required this run; column comments mark `customer_name` as PII for future governance | PROPOSED |
| Sample-data fallback | children always use the fixture layer (`run_mode: fixture`); only the parent live window on NS=demo counts | FACT S7 orchestration policy |
| Decommission criteria | per unit: recon green in the parent live window, cron line retired, consumer re-pointed, 1 clean scheduled cycle | PROPOSED |

Cross-profile reconciliation: the runbook's `otterworks.custbill_*` catalog naming is superseded by `ow_tp.{bronze,silver,gold}` (S1, S5 §8) — deliberate, recorded in `06_decisions.md` D-001. The contracts README's 3-PR stack is superseded by one-PR-per-unit (S7) — deliberate, D-002.

## Open questions for STOP A
1. Confirm all PROPOSED rows above (batch confirmation).
2. Named owner of the mainframe SFTP transfer (D7-1) and the finance recipient list (D4-1).
3. Security reviewer contact and cutover-principal holder (intake §3/§5 OPEN).
