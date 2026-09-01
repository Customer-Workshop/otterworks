# DBX Migration Intake — Commission Pay `COMMISSION_DW` (Oracle) → Databricks lakehouse

Front door: `!dbx_migrate_warehouse` (SQL warehouse family). Run branch: `tp-run/databricks-20260901T205306Z` (cut from `tech-partnerships` via `make tp-run-branch TRACK=databricks`).

Every row is **FACT** (stated by the engagement), **DISCOVERED** (probed live on 2026-09-01 against the fixture brought up with `make insurance-up NS=intake`), or **PROPOSED** (default to confirm once at STOP A). Probe SQL and raw output: `/home/ubuntu/intake/probe_dw.sql`, `probe_dw.out`, `probe_counts.out` (session-local; the queries are reproduced in §7 so any session can re-run them).

## 1. Source estate
| Field | Value | Status | Notes |
|---|---|---|---|
| Source system + version | Oracle Database Free `23.26.3.0.0` (banner "Oracle AI Database 26ai Free"), PDB `FREEPDB1`, schema `COMMISSION_DW` | DISCOVERED | `SELECT banner_full FROM v$version` |
| How it is reached | `make insurance-up NS=<ns>`; listener on `127.0.0.1:<51521 + crc32(NS)%1000>` (NS=intake → `127.0.0.1:51619`); `sqlplus commission_dw/commission_dw@localhost:1521/FREEPDB1` inside container `otterworks-insurance-<ns>-insurance-oracle-1` | DISCOVERED | Loopback-only binding; see §3 federation row |
| Scope | `COMMISSION_DW` only. `COMMISSION_PKG` (OLTP business rules in `COMMISSION_PAY`) is **out of scope** | FACT | The DW's ETL still *reads* `COMMISSION_PAY` — that is a D3 upstream feed, not scope creep |
| Estate headline size | 5 tables (`DIM_AGENT`, `DIM_PRODUCT`, `DIM_PERIOD`, `FACT_COMMISSION`, MV container `MV_AGENT_COMMISSION_SUMMARY`), 1 materialized view (`MV_AGENT_COMMISSION_SUMMARY`, refresh DEMAND / COMPLETE, build IMMEDIATE), 1 PL/SQL package `DW_ETL_PKG` (spec 8 + body 80 lines; `LOAD_COMMISSION_FACTS`, MERGE-based, idempotent), 4 identity sequences, 9 indexes (8 system constraint indexes + `UX_FACT_ROW`), 0 views, 0 scheduler jobs visible | DISCOVERED | `all_objects`, `all_mviews`, `all_source` as `COMMISSION_DW` |
| Current data volume | All five DW tables hold **0 rows** at fixture boot; the DW is populated only when `DW_ETL_PKG.LOAD_COMMISSION_FACTS` runs (the `make insurance-test NS=<ns>` OLAP suite invokes it) | DISCOVERED | Golden-baseline recording must run the ETL deterministically first (`scripts/tp-run-deterministic.sh`) |
| Lineage (in-estate) | `DW_ETL_PKG` → writes `DIM_*`, `FACT_COMMISSION`; `MV_AGENT_COMMISSION_SUMMARY` ← `DIM_AGENT`, `DIM_PRODUCT`, `DIM_PERIOD`, `FACT_COMMISSION` | DISCOVERED | `all_dependencies WHERE owner='COMMISSION_DW'` |
| What loads it | `DW_ETL_PKG.LOAD_COMMISSION_FACTS` reading `COMMISSION_PAY.AGENTS`, `.PRODUCTS`, `.POLICIES`, `.COMMISSION_LEDGER` (cross-schema, via `GRANT SELECT ANY TABLE ON SCHEMA commission_pay TO commission_dw`). No external ingestion tool, no scheduler entry visible | DISCOVERED | Register as **D3** (upstream feed owned by a non-migrating system); trigger/batch granularity is "per period, on demand" — a contract ambiguity class to pin at STOP A |
| What reads it | No evidence. Object grants on `COMMISSION_DW` objects: only `PUBLIC … INHERIT PRIVILEGES` (no SELECT grants to any consumer). No BI tool or downstream extract is declared | DISCOVERED | **D4 evidence gap** — see next row |
| Query history available? | **No.** `V$SQL`, `DBA_HIST_SQLTEXT` (AWR) and `UNIFIED_AUDIT_TRAIL` all raise ORA-00942 for `COMMISSION_DW` (privileges: CREATE SESSION/TABLE/VIEW/SEQUENCE/PROCEDURE/MATERIALIZED VIEW only) | DISCOVERED | Consumer detection cannot use query history. Granting `SELECT_CATALOG_ROLE` would modify the legacy system → forbidden. D4 sweep falls back to grants (empty) + repo-wide code search for `COMMISSION_DW`/`MV_AGENT_COMMISSION_SUMMARY` references. Recorded as **D4-evidence gap** at intake, not deferred |

## 2. Target
| Field | Value | Status | Notes |
|---|---|---|---|
| Databricks workspace | secret `DATABRICKS_DEMO_HOST` (shared demo workspace) | FACT (knowledge) | — |
| Warehouse / compute | Serverless SQL warehouse `565cd2fd713738c4` "Serverless Starter Warehouse" (RUNNING). Never create clusters | DISCOVERED | `make tp-preflight-databricks` |
| Target catalog / schema layout | `ow_tp` catalog, schemas `bronze` / `silver` / `gold` / `ops`, objects suffixed `_<ns>` (medallion, per existing runbook convention). **`ow_tp` does not currently exist in the workspace** (preflight: 3 of 10 probes DENIED with `Catalog 'ow_tp' does not exist`; `SHOW CATALOGS` → banking_analytics, de_demo_workspace, migration_demo, redshift_src, ricky_kartolo, samples, system, tsql_demo) | DISCOVERED | Wave-0 item: recreate `ow_tp` + four schemas (permitted: `ow_tp` prefix is our namespace). Re-run preflight until 10/10 VERIFIED before any child launches |
| Namespace for this run | `NS=cdw` (rehearsal, torn down after) | PROPOSED | `demo` is reserved for the staged, never-broken story |
| Repo for migrated code + docs | `Cognition-Partner-Workshops/otterworks`, branch `tp-run/databricks-20260901T205306Z`; `.migration/` in repo root; contracts under `docs/tech-partnerships/contracts/` (schemas exist: `unit-contract.schema.json`, `recon-report.schema.json`) | FACT | Never PR into `tech-partnerships` or `main` |

## 3. Access
| Field | Value | Status | Notes |
|---|---|---|---|
| Legacy read-only credential | Fixture user `commission_dw` (well-known fixture credential, loopback only). Assessment tier = this user; it can also DDL in its own schema, so **the harness must never call DDL/DML as it** | DISCOVERED | Playbook rule: legacy is read-only in every phase |
| Databricks credential | secret `DATABRICKS_DEMO_TOKEN` — scopes sql, unity-catalog, jobs, secrets, workspace, files verified by preflight (files probes only failed on the missing catalog, not on scope) | DISCOVERED | Migration tier; write only to `ow_tp` |
| Federation / JDBC path approvable? | **Not reachable by topology.** Source binds `127.0.0.1` inside a local Docker Compose project; the Databricks workspace has no network path to it. Existing UC connections: `redshift_demo` (REDSHIFT) + system HTTP connections only — no Oracle connection. (Lakehouse Federation lists Oracle as a supported source, I believe, so this is a topology limit, not a product one.) | DISCOVERED | **D10**: federation N/A → coexistence + recon fall back to **snapshots** landed through the transport fixture (`make tp-fixture-land` / `tp-fixture-verify`, byte-checksummed). Recon mode **DEGRADED** (see §4) |
| Security reviewer contact | — | OPEN | Ask at STOP A (fixture has none; name a placeholder owner or mark N/A) |

## 4. Correctness contract
| Field | Value | Status | Notes |
|---|---|---|---|
| Recon mode | **DEGRADED** (snapshot manifests with source, extraction time, row counts; every recon header names the mode) | DISCOVERED→PROPOSED | Forced by the federation row; LIVE is not available |
| Numeric tolerances | Exact match. Commission amounts compared in **cents as integers**; `NUMBER` → `DECIMAL(p,s)` with Oracle precision preserved; Oracle `ROUND` (half away from zero) vs Spark `ROUND` (HALF_UP on DECIMAL — same result for positive amounts; negatives must be tested) is a named dictionary entry | PROPOSED | Population: every `FACT_COMMISSION` row and every MV row |
| Timestamps / dates | `DATE` → `DATE` (day precision, no tz); `TRUNC(d,'MM')`-style period derivation → `date_trunc`; compare as ISO strings | PROPOSED | Dictionary entry |
| Row-diff size threshold | Full row-level diff everywhere (estate is tiny; threshold irrelevant, set 1,000,000 rows) | PROPOSED | — |
| Legacy query concurrency cap | 2 concurrent read sessions against the fixture | PROPOSED | Oracle Free: 2 CPU threads |
| Idempotency proof | Rerun `LOAD_COMMISSION_FACTS`-equivalent for the same period; row set must be identical (legacy MERGE semantics) **excluding `FACT_COMMISSION.loaded_at`** | PROPOSED | Matches `make tp-validate-recon` requirement |
| Server-side timestamps | `FACT_COMMISSION.loaded_at` (`DEFAULT SYSTIMESTAMP`, rewritten to `SYSTIMESTAMP` on every MERGE update) is **excluded from baselines, row diffs and idempotency checks** and normalized to NULL in snapshot extracts. `TP_FAKETIME`/libfaketime only freezes the launching host process; Oracle evaluates `SYSTIMESTAMP` inside the already-running container, so it cannot be frozen from the harness | PROPOSED | Recon key for the fact table is `UX_FACT_ROW`'s columns, never `fact_id`/`loaded_at` |

## 5. Process
| Field | Value | Status | Notes |
|---|---|---|---|
| Stop routing | Blocking STOPs (A/B/C/E) → Slack `#ow-migrations`; emergency halts (write-target collision, circuit breaker) → `#ow-tp-alerts`; wave closes (STOP D) → `#ow-tp-status`. Approve by replying in-thread. Nothing else pings | FACT | — |
| Message style | 2–4 short sentences, lead with the decision, state the recommended answer and the exact approving reply, link artifacts | FACT (plugin rule) | Audience-facing surfaces stay in-character about the legacy estate |
| Daily digest | Off | PROPOSED | — |
| Question style | One at a time, with options | PROPOSED | — |
| PR reviewer(s) + SLA | Engagement lead; 2 review rounds per PR; `tp-pre-pr-self-check` skill before opening; one PR per unit, never stacks | FACT (knowledge) | — |
| Unit branch naming | `migrate/commission-dw/<wave>-<unit>` off the run branch; PR target = run branch | PROPOSED | — |
| Fan-out width | Pilot ≤ 3, then ≤ 5 — the estate is ~5 units, so width is bounded by the unit count | PROPOSED | — |
| Data-load posture | **Backfill-first via snapshot** (federation unavailable): land deterministic extracts of `COMMISSION_DW` tables *and* of the D3 upstream `COMMISSION_PAY` inputs to bronze, rebuild silver/gold from the converted ETL, recon against the landed DW snapshot | PROPOSED | — |
| Cutover principal holder | — | OPEN | Ask at STOP A |

## 6. Warehouse-family defaults recorded for the chain
- **Unit** = table / materialized view / package procedure. Candidate units (inventory confirms at STOP B): `DIM_AGENT`, `DIM_PRODUCT`, `DIM_PERIOD`, `FACT_COMMISSION` (bronze→silver), `DW_ETL_PKG.LOAD_COMMISSION_FACTS` (the conversion unit, PL/SQL → Spark SQL/DLT MERGE), `MV_AGENT_COMMISSION_SUMMARY` (gold table or DLT materialized view).
- **Lineage extraction** = `all_dependencies` + `all_source` + `all_mviews` (catalog metadata). Query history is unavailable (§1) — the D4 sweep is grant-based + code search only.
- **SQL profile** is the dominant surface; one **procedural** unit (`DW_ETL_PKG`, 88 lines PL/SQL) — weight it highest in complexity ranking per the family advice.
- **Physical design dictionary** (named concern, to be authored in the plan): surrogate keys (`agent_key`, `product_key`, `period_key`, `fact_id`) are Oracle `GENERATED BY DEFAULT ON NULL AS IDENTITY` — the backfill **preserves source key values** (plain `BIGINT`, loaded explicitly, so `FACT_COMMISSION.*_key` foreign keys stay valid without remapping); Databricks `GENERATED ALWAYS AS IDENTITY` is *not* used because it rejects explicit values; identity generation resumes only in the converted loader for post-cutover rows (`GENERATED BY DEFAULT AS IDENTITY (START WITH <max+1>)`, set after backfill); `UX_FACT_ROW` unique index → recon key + `MERGE` key (Delta has no unique constraints); constraint indexes → dropped; MV (COMPLETE/DEMAND) → gold Delta table rebuilt by job or DLT MV; no dist/sort keys or partitioning exist to translate; liquid clustering on `FACT_COMMISSION(period_key, agent_key)` proposed.
- **Dialect concerns** for the dictionary: `NUMBER` precision, `DATE` (no tz), `ROUND`/`TRUNC`, `NVL`/`DECODE`, `MERGE` semantics, `SYSTIMESTAMP` (server-side, unfreezable — see §4 `loaded_at` row), `WHEN OTHERS` handling if present.
- **Coexistence** = snapshot-based (federation-first is the family default but is topologically unavailable here — recorded, not assumed).
- **Dialect skill**: no `oracle-plsql` dialect skill exists in the dbx-migration plugin (available: `redshift-sql`, `teradata-bteq`, `informatica-xml`). Repo skills `oracle-billing-estate` / `stored-procs-to-microservices` cover fixture operation and proc→service parity, not SQL translation. **Conversion proceeds on generic ANSI translation plus the dictionary above; building `oracle-plsql` as a dialect skill is a wave-0 item.**

## 7. Dependencies registered at intake
| ID | Class | Item | Status |
|---|---|---|---|
| D3-1 | D3 | `DW_ETL_PKG` reads `COMMISSION_PAY.AGENTS/PRODUCTS/POLICIES/COMMISSION_LEDGER` (out-of-scope schema). Needs an ingestion contract: snapshot those four tables as bronze inputs | OPEN → plan |
| D4-1 | D4 | No consumers detectable: query history not granted, no object grants. Evidence gap declared; code-search sweep in inventory | OPEN → inventory |
| D10-1 | D10 | Lakehouse Federation to source not reachable (loopback fixture) → snapshot fallback, recon DEGRADED | ACCEPTED at intake, confirm at STOP A |
| D10-2 | D10 | `ow_tp` catalog absent in workspace; preflight 7/10 | OPEN → wave 0 (create catalog + schemas, re-run `make tp-preflight-databricks`) |
| D10-3 | D10 | Query-history views (`V$SQL`, AWR) not granted to assessment user; **not** requestable (would modify legacy) | ACCEPTED |
| W0-1 | wave 0 | Build `oracle-plsql` dialect skill (stub) | OPEN |
| W0-2 | wave 0 | Record golden baseline: (a) run `DW_ETL_PKG.LOAD_COMMISSION_FACTS` + `DBMS_MVIEW.REFRESH('MV_AGENT_COMMISSION_SUMMARY')` via `scripts/tp-run-deterministic.sh` (`TZ=UTC`, seeded fixture data); (b) extract with a read-only `sqlplus` spool as `commission_dw` — one UTF-8 CSV per object (4 DW tables, the MV, and the 4 `COMMISSION_PAY` inputs), `ORDER BY` primary key (the MV has none: order by its grouping columns `agent_code, period_month, line_of_business`, which are unique per row given `full_name` is functionally dependent on `agent_code`), `loaded_at` emitted as empty, plus a `manifest.json` (object, row count, sha256, extraction time) — into `etl/legacy-extra/commission_dw/<ns>/`; (c) land **that directory explicitly**: `FIXTURE_SOURCE=etl/legacy-extra/commission_dw/<ns> make tp-fixture-land NS=<ns>` then `make tp-fixture-verify NS=<ns>`. The target's default `--source etl/legacy-extra` is the CUSTBILL batch estate and only copies files — never call it without `FIXTURE_SOURCE` for this estate; verification must additionally assert the 9 expected object files are present with manifest row counts > 0 | OPEN |

## 8. Re-runnable probe (as `commission_dw`)
```sql
SELECT banner_full FROM v$version;
SELECT object_type, COUNT(*) FROM all_objects WHERE owner='COMMISSION_DW' GROUP BY object_type;
SELECT name, type, referenced_owner, referenced_name FROM all_dependencies WHERE owner='COMMISSION_DW';
SELECT mview_name, refresh_mode, refresh_method FROM all_mviews WHERE owner='COMMISSION_DW';
SELECT grantee, table_name, privilege FROM all_tab_privs WHERE table_schema='COMMISSION_DW';
SELECT COUNT(*) FROM v$sql;            -- ORA-00942: query history not available
SELECT COUNT(*) FROM dba_hist_sqltext; -- ORA-00942
```

## 9. Hand-off
Intake complete: engine pinned, catalog access probed, dialect posture recorded (generic ANSI + W0-1), family defaults set. Next: `!dbx_migrate_pipeline` on branch `tp-run/databricks-20260901T205306Z`, consuming this file. STOP A must resolve the OPEN rows (security reviewer, cutover principal) and confirm every PROPOSED row.
