# .migration/00_context.md — engagement context (front-door intake)

Written by `!dbx_migrate_etl` (Front Door: ETL Tool Estate). Every row is FACT (user-stated),
DISCOVERED (probed in the repo/environment), or PROPOSED (default; confirm at STOP A).
The orchestrator (`!dbx_migrate_pipeline`) begins with `!dbx_migration_setup`, which extends
this file and adds `01`–`07`; nothing here is to be re-asked.

## 1. Engagement

| Field | Value | Provenance |
|---|---|---|
| Customer / estate | OtterWorks ETL box `otterworks-etl-prod-01` — `etl/` (Python cron estate, 2014) + `etl/legacy-extra/` (CUSTBILL polyglot batch chain, 1998–2014) | FACT |
| Source family | ETL estate, **no ETL tool**: hand-rolled scripts scheduled by system cron. Source "export" = the git tree itself (`etl/**` on `tech-partnerships`). | FACT + DISCOVERED |
| Source "tool + version" (pinned) | cron (vixie crontab, `/etc/crontab` style) · bash · ksh (KornShell, real `ksh` binary required) · Perl 5.005-style, no modules · Python 3 with `boto3==1.26.0`, `psycopg2-binary==2.9.3`, `pandas==1.3.5`, `requests==2.27.0` | DISCOVERED (`etl/requirements.txt`, `etl/run.sh`, shebangs) |
| Target | Databricks lakehouse: Unity Catalog `ow_tp` (schemas `bronze`/`silver`/`gold`), Delta, serverless SQL warehouse + serverless notebook tasks, Jobs/DLT, `/Volumes/ow_tp/bronze/landing`, secret scope `ow_tp`, notebooks `/Shared/ow_tp` | FACT (user: "→ lakehouse") + DISCOVERED (`docs/tech-partnerships/contracts/README.md`) |
| Scope | **All nine jobs** (see §3). One pipeline = the whole estate; STOP B confirms this boundary rather than picking a slice. | FACT |
| Repo / branches | `Cognition-Partner-Workshops/otterworks`. Legacy before-state: `tech-partnerships` (read-only, never a PR target). Run branch (this run): **`tp-run/databricks-20260901T205308Z`** (cut with `make tp-run-branch TRACK=databricks`). Every unit PR targets the run branch. | FACT + DISCOVERED |
| Artifacts | `.migration/` in this repo on the run branch; contracts in `docs/tech-partnerships/contracts/` | DISCOVERED |
| Track | databricks | FACT |

## 2. Notification & interaction contract

| Event | Channel | Provenance |
|---|---|---|
| Blocking STOPs A / B / C / E (artifacts ready, one decision each) | Slack `#ow-migrations` (`C0BQP3P965V`) | FACT |
| Fan-out halts (write-target collision, circuit breaker) and emergency halts | Slack `#ow-tp-alerts` (`C0BQP3LU3JT`) | FACT |
| Wave close (STOP D, notify-only: exception count + wave report + wave-close brief) | Slack `#ow-tp-status` (`C0BRYRE5ZQQ`) | FACT |
| Everything else (per-child, per-green-PR) | never posted | FACT (kit rule) |

All three channels verified readable+writable by this session (`lookup_slack_resource`).
Message style per kit: 2–4 sentences, lead with the decision, recommended answer + exact approval
reply, link the artifact. Question style: one at a time, options where the set is small.
Audience-facing surfaces (Slack, Jira OTD, Confluence OWTP, PR bodies) treat the estate as a
genuine production legacy system.

## 3. Unit inventory seed (unit = script + its cron line)

Nine units. Scheduler is **system cron only** (no Control-M/Autosys): the scheduler workstream
is in-house, not dual-team; the crontab comments are the only scheduler documentation.

| # | Unit | Lang / vintage | Cron (`etl/legacy-extra/crontab`) | Sources → sinks (headline) | LOC |
|---|---|---|---|---|---|
| 1 | `analytics_daily.py` | Python 2014 | `0 2 * * *` | SQS + DynamoDB events → S3 gzip JSON (`analytics/daily`) + PostgreSQL `otterworks_analytics` | 452 |
| 2 | `audit_archive_weekly.py` | Python 2014 | `0 3 * * 0` | DynamoDB (>90d) → JSONL.gz → S3 Glacier; batch-delete from DynamoDB | 224 |
| 3 | `search_reindex_weekly.py` | Python 2014 | `0 4 * * 0` | document-service + file-service REST → MeiliSearch (clear + bulk index) | 319 |
| 4 | `storage_cleanup_daily.py` | Python 2014 | `30 2 * * *` | S3 listing vs DynamoDB metadata → quarantine bucket + savings report | 217 |
| 5 | `user_activity_daily.py` | Python 2014 | `0 5 * * *` | PostgreSQL aggregates + per-user S3 → S3 `reports/user-activity/<ds>/activity_report.json` (read by admin-service) | 255 |
| 6 | `sftp_ingest_poll.ksh` | ksh 1998 (ported 2014) | `*/15 * * * *` | mainframe SFTP drop (`sftp-drop/upload`) → `incoming/` + `archive/` | 70 |
| 7 | `parse_custbill_fixedwidth.sh` | bash+sed/awk/cut 2001 | `5-59/15 * * * *` | `incoming/CUSTBILL_*.dat` (copybook CBCUST01 fixed-width) → `parsed/*.psv` | 81 |
| 8 | `finance_excel_report.pl` | Perl 2004 | `10 2 * * *` | `parsed/*.psv` → `reports/finance_billing_YYYYMMDD.csv` + byte-identical `.xls`; sendmail pipe (no-op) | 91 |
| 9 | `run_all.sh` (+ estate rollup) | bash 2014 | `0 6 * * 0` | chains 6→7→8 with `sleep 600` | 28 |

Shared: `etl/run.sh`, `etl/config.ini` (plaintext AWS/DB/MeiliSearch credentials — treat as
compromised-by-design; never copy values), `/tmp/*.lock` files (never removed).
Estate size: 9 jobs, ~1.7k LOC, 1 crontab, 2 upgrade guides whose deficiency tables are the
acceptance checklists (`etl/ETL_UPGRADE_GUIDE.md`, `etl/legacy-extra/ETL_UPGRADE_GUIDE_ADDENDUM.md`).

Golden legacy baselines are deterministic per namespace (`make legacy-etl-gen-data NS=demo`,
`make legacy-etl-run JOB=run_all`, `OTTERWORKS_LEGACY_ROOT` isolated per child); NS=demo
yields 100 CUSTBILL rows and a six-row finance report (see `docs/tech-partnerships/runbook-databricks.md`).

## 4. Family defaults (ETL-estate profile, set by the front door)

| Default | Value |
|---|---|
| Unit | one script + its cron line(s) + `run.sh`/`config.ini` slice it reads |
| Lineage extraction | parser-based from source (crontab lines, `config.ini` keys, boto3/psycopg2/requests call sites, file globs) — **not** query history (none exists) |
| Dominant workload surface | PIPELINE (batch ETL); no BI/ML surface in scope |
| Scheduler edges | first-class **D5** entries: every cron line, the :00/:05 ingest–parse overlap, 02:00/02:10 analytics–finance overlap, Sunday `run_all` re-run of everything |
| Parameter/config indirection | named inventory risk: hostname `if`-blocks selecting `/data/otterworks` vs `/data2/otterworks_uat`, `config.ini` shared by all Python jobs, `OTTERWORKS_LEGACY_ROOT` env override |
| Data-load posture | PROPOSED: fixture-first per child (`run_mode: fixture` via local fixture layer / LocalStack), single parent-owned live recon window per wave on NS=demo |
| Recon mode | PROPOSED: LIVE dual-run against legacy outputs regenerated from the deterministic seed; exact match (row parity on all 6 CUSTBILL fields, aggregate parity to the cent) |
| PR shape | one PR per unit into the run branch (org policy, measured); `make tp-smoke` gate; recon JSON validated by `make tp-validate-recon` |
| Fan-out | PROPOSED: wave 0 shared objects serial (catalog/schemas/volume/scope), wave 1 pilot ≤5 (CUSTBILL chain 6–8 + one Python job), wave 2 the rest; width ≤ 9 total so no dynamic workflow required unless the orchestrator prefers it |

## 5. Source-dialect skill

No catalog skill exists for a **cron/bash/ksh/Perl/Python-script** estate (catalog has
`informatica-xml`, `teradata-bteq`, `redshift-sql` only). Repo-level skill
`.agents/skills/legacy-etl-demo` covers running/verifying the CUSTBILL chain (not conversion).
Inventory can run generically; conversion quality depends on a dialect skill, so **building
`cron-shell-perl-python` dialect notes is wave-0 work**, and extractor hardening (hostname
branching, `config.ini` indirection, `2>/dev/null || true` suppression, fixed-width slicing)
is budgeted as engineering on this first engagement. Kit target skills apply unchanged:
`unity-catalog-conventions`, `dlt-pipelines`, `asset-bundles`, `data-reconciliation`,
`databricks-auth-cli`, `backfill-planner`.

## 6. Dependency register seed (to be carried into `04_dependency_register.md`)

| ID | Class | Contract | Status / fired request |
|---|---|---|---|
| D10-1 | env/access | Databricks target catalog `ow_tp` **does not exist** in the workspace: `make tp-preflight PLATFORM=databricks` → 3/10 probes DENIED (`files-get-directory`, `files-put-get`, `uc-create-list`: "Catalog 'ow_tp' does not exist"); jobs/secret-scope/serverless-warehouse probes VERIFIED (warehouse `Serverless Starter Warehouse`, id `565cd2fd713738c4`). Manifest `.tp-preflight/databricks-capabilities.json`. | OPEN — wave-0 parent task: create `ow_tp` + `bronze/silver/gold` + managed volume `bronze.landing` (shared Terraform, parent-owned), then re-run preflight to a clean manifest before any child launches. |
| D10-2 | env/access | `infrastructure/terraform-databricks/` and the per-unit contract files referenced by `docs/tech-partnerships/contracts/README.md` are absent from `tech-partnerships`; only `README.md` + `schema/` exist. | OPEN — setup/inventory must author them (`make tp-validate-contracts` currently expected to fail until contracts exist). |
| D10-3 | env/access | Legacy runtime prerequisites for golden baselines: `ksh` package, docker + `sshpass` for the SFTP fixture; LocalStack/compose for the Python jobs' SQS/DynamoDB/S3/Postgres/MeiliSearch sources. | Probe in setup; record WORKS/BLOCKED with evidence. |
| D5-1..5 | scheduler | Cron lines for units 1–9 incl. the documented overlaps (ingest/parse :00/:05 half-written reads; finance 02:10 vs analytics 02:00; Sunday `run_all` overlaps all). Target: Workflow/DLT with `max_active_runs=1`, event/DAG dependencies, alerting. | Register per unit at inventory; decision = re-point to Databricks Workflows, cron lines retired at cutover. |
| D7-1 | external hand-off | Mainframe CUSTBILL drop via SFTP (`mvsprod@…`, `upload/`). Target per runbook: S3 Transfer Family → Auto Loader. Owner: mainframe team (unnamed). | Contract needed at STOP A: who repoints the mainframe transfer; encoding/byte transparency, malformed-record policy, empty-input semantics, batch granularity must be fixed in the unit contract. |
| D4-1 | consumer | `finance-reports@otterworks.dev` distribution of `finance_billing_*.xls` (currently a silent no-op sendmail; `jake@` still listed). | Decide delivery mechanism + managed recipient list at plan. |
| D4-2 | consumer | admin-service reads `s3://…/reports/user-activity/<ds>/activity_report.json`. | Keep path/shape or re-point admin-service — decide at plan. |
| D3-1 | upstream feed | document-service / file-service REST APIs paginated by `search_reindex_weekly.py`; MeiliSearch is the sink. | Lakehouse role for a search reindex is a scope decision at STOP B/C (candidate: keep as a Job, not a table pipeline). |
| D8-1 | governance | `config.ini` holds plaintext AWS keys, DB password, MeiliSearch master key. | Target: secret scope `ow_tp` by name only; never copy values. |

## 7. Access posture (names only)

Databricks: `DATABRICKS_DEMO_HOST` / `DATABRICKS_DEMO_TOKEN` (shared demo workspace; `ow_tp`
prefix everywhere; serverless only; no clusters). AWS: `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` (serverless/on-demand only, tag `Project=otterworks-tp`, prefix `ow-tp-`).
Legacy: read-only git tree + deterministic local fixtures; no production legacy host access
exists or is requested. Cutover principal: customer-held, not in any Devin secret.

## 8. Known deviations to reconcile at setup

- `docs/tech-partnerships/contracts/README.md` prescribes a 3-PR stacked series per unit;
  org policy (measured rehearsal) is **one PR per unit**. Front door records org policy as the
  default; setup confirms at STOP A.
- Runbook names the target catalog `otterworks.custbill_*`; contracts README and preflight use
  `ow_tp.{bronze,silver,gold}`. `ow_tp` is authoritative (shared-workspace prefix rule).

## 9. Setup (appended by `!dbx_migration_setup`, 2026-09-01)

- Target state: `docs/tech-partnerships/OtterWorks_ETL_target_state.md` v1.0-draft (CORE + PIPELINE, ORCHESTRATION, CONSUMER, DATA/DEPENDENCY; SQL and ML-SCORING N/A).
- Parity contract: `.migration/03_recon_tolerances.md` v1 (LIVE dual-run, exact match).
- Access posture after probes (`07_access_checklist.md`): Databricks auth WORKS and the token can CREATE CATALOG (probe catalog created and dropped), so D10-1 needs no customer action; legacy baseline regeneration WORKS (NS=demo report matches); AWS WORKS but `AWS_DEFAULT_REGION` is unset on the VM (D10-4); `make tp-smoke` green in 12.6 s.
- Designated write area (kit guardrail): Unity Catalog `ow_tp` only; AWS `ow-tp-*` serverless only.
- Interaction contract: blocking stops are posted to `#ow-migrations` and approved by an in-thread reply; the same stop is mirrored in the web session. One question at a time, options offered where the set is small. Daily digest: off.
