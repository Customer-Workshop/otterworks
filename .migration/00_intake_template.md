# DBX Migration Intake — OtterWorks ETL box → lakehouse (filled by the front door)

Each value is tagged **FACT** (user), **DISCOVERED** (probed), or **PROPOSED** (default; confirm at STOP A).
No template was supplied by the user; all rows were filled by probing or defaulting.

## 1. Source estate
| Field | Value | Tag |
|---|---|---|
| Source system + version | No ETL tool. System cron + bash / ksh (1998) / Perl 5.005-style (2004) / Python 3 (boto3 1.26, psycopg2 2.9.3, pandas 1.3.5, requests 2.27) scripts, 2014 vintage | DISCOVERED |
| Estate headline size | 9 jobs (5 Python, 1 ksh, 1 bash parser, 1 Perl, 1 bash chain), 1 crontab (9 lines), ~1.7k LOC, 1 shared `config.ini`, 1 `run.sh` | DISCOVERED |
| What loads it / what reads it | Loads: mainframe SFTP CUSTBILL drop; SQS/DynamoDB events; S3 buckets; PostgreSQL `otterworks_analytics`; document-/file-service REST. Reads: finance distribution list (`.xls` report), admin-service (`reports/user-activity/*.json`), MeiliSearch, S3 data lake / Glacier archive | DISCOVERED |
| Query history available? | No (no warehouse). Consumer detection is parser-based from source + crontab | DISCOVERED |
| Export mechanism | Git tree `etl/**` on `tech-partnerships` — complete, read-only; no D10 for export | DISCOVERED |

## 2. Target
| Field | Value | Tag |
|---|---|---|
| Databricks workspace URL(s) | `${DATABRICKS_DEMO_HOST}` (shared demo workspace) | DISCOVERED |
| Target catalog / schema layout | `ow_tp.bronze` / `ow_tp.silver` / `ow_tp.gold`, volume `/Volumes/ow_tp/bronze/landing`, secret scope `ow_tp`, notebooks `/Shared/ow_tp`, jobs `ow_tp_<unit>`, `ns` column/param on everything (`demo` this run). **Catalog `ow_tp` currently absent (preflight DENIED 3/10) — wave-0 parent task.** | DISCOVERED |
| Warehouse / compute to use | Serverless SQL warehouse `Serverless Starter Warehouse` (`565cd2fd713738c4`) + serverless notebook tasks; never create clusters | DISCOVERED |
| Repo(s) for migrated code + docs | `Cognition-Partner-Workshops/otterworks`, run branch `tp-run/databricks-20260901T205308Z` (off `tech-partnerships`); `.migration/` + `docs/tech-partnerships/contracts/` | FACT + DISCOVERED |

## 3. Access
| Field | Value | Tag |
|---|---|---|
| Legacy read-only credential (secret name) | none needed — legacy is the git tree + deterministic local fixtures (`make legacy-etl-gen-data NS=<ns>`, LocalStack/compose) | DISCOVERED |
| Databricks credential (secret name) | `DATABRICKS_DEMO_HOST` / `DATABRICKS_DEMO_TOKEN` (scopes incl. files verified previously; catalog missing now) | DISCOVERED |
| AWS credential (secret name) | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (serverless only, tag `Project=otterworks-tp`, prefix `ow-tp-`) | DISCOVERED |
| Federation / JDBC path approvable? | N/A — no legacy database engine to federate; recon is dual-run against regenerated legacy outputs | PROPOSED |
| Security reviewer contact | unknown — ask at STOP A | OPEN |

## 4. Correctness contract
| Field | Value | Tag |
|---|---|---|
| Recon mode | LIVE dual-run: legacy chain re-run from the deterministic seed per namespace vs lakehouse output | PROPOSED |
| Numeric tolerances | exact match: CUSTBILL amounts to the cent (2 dp), counts exact, dates ISO exact; Python jobs: exact on aggregates, byte-identical where the legacy artifact is a file | PROPOSED |
| Row-diff size threshold | full row diff (estate ≤ 10^4 rows per ns); keyed sampling not needed | PROPOSED |
| Legacy query concurrency cap | N/A (no live legacy engine); one parent-owned live window per wave on Databricks | PROPOSED |
| Anomaly policy | converted pipelines must reject what legacy passed (invalid dates, bad implied decimals, trailer mismatches) → quarantine table; planted anomalies compared as sets | PROPOSED |

## 5. Process
| Field | Value | Tag |
|---|---|---|
| Stop routing | Slack: STOPs A/B/C/E → `#ow-migrations`; halts → `#ow-tp-alerts`; wave closes (STOP D) → `#ow-tp-status`. Approve by replying in-thread. | FACT |
| Daily digest | off | PROPOSED |
| Question style | one at a time, with options | PROPOSED |
| PR reviewer(s) + turnaround SLA | requester; 2 review rounds per PR budget; `make tp-smoke` + recon JSON gate | PROPOSED |
| Fan-out width preference | pilot ≤5 (CUSTBILL chain + 1 Python job), then remaining Python jobs + rollup; one PR per unit into the run branch | PROPOSED |
| Data-load posture | fixture-first per child (`run_mode: fixture`), parent single live recon window on `NS=demo`; no backfill of production history in scope (history generator available via `make legacy-etl-gen-history` if wanted) | PROPOSED |
| Cutover principal holder | customer-held; not a Devin secret; named at STOP A | OPEN |
