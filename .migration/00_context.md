# 00_context — Oracle OW_BILLING -> MongoDB Atlas (mmp_rt_billing)

Engagement id: `mmp-rt-live-20260926`. Orchestrator session: https://partner-workshops.devinenterprise.com/sessions/96b8955d22a2477ba2cffcbc67cab7a9
Plugin: mongo-migration 0.3.0. Playbooks: [MONGO v1] 0-5. Profile loaded: `profiles/oracle.md`.

Each field is FACT (intake), DISCOVERED (probed), or PROPOSED (defaulted, confirmed at STOP A).

## 1. Source
| Field | Value | Kind |
|---|---|---|
| Source family | `oracle` (Oracle Database Free 23, PDB `FREEPDB1`, schema `OW_BILLING`) | FACT |
| Location | `localhost:52521` on the orchestrator VM only (docker `otterworks-oracle-billing-oracle-billing-1`, internal 1521) | FACT |
| Headline size | ~10 tables (CUSTOMER_MASTER 25000 rows/155 cols, INVOICE_HEADER 18750, INVOICE_LINE 150000 with 37 orphans, ENTITY_ATTR_VALUE 8333, TENANTS shared across namespaces), 5 PL/SQL packages, jobs in `schema/04_jobs.sql`. Full census in `07_dependency_register.md` (phase 2). | FACT |
| Seeded namespace | `NS=mmprt SCALE=demo` via `make oracle-billing-seed`; seed manifest `testdata/legacy/manifests/mmprt.json` (git-ignored) | FACT |
| Application code | `services/legacy-billing/` (Flask; `app/backends/oracle.py`, `app/oracle_conn.py`, `bridge/bridge.py`); PL/SQL `services/legacy-billing/db/oracle/packages/`; DDL `services/legacy-billing/db/oracle/schema/` | FACT |
| Who else reads/writes | DBMS_SCHEDULER jobs (`schema/04_jobs.sql`), `_HIST` triggers, autonomous audit logging; owners in `07_dependency_register.md` | FACT (headline) |
| Source mode | `live` | FACT |
| Children can reach the source? | **No.** Child sessions run on other machines and cannot reach `localhost:52521`. Consequence (playbook 1 step 1): fan-out children cannot do the one live read or run live recon; every live read and every recon runs on this VM. The wave plan at STOP B chooses the single-session path (or local subagents) accordingly. | FACT |

## 2. Target
| Field | Value | Kind |
|---|---|---|
| Atlas project / cluster | `otterworks-demos` / `otterworks-demo` (shared M0 free tier; demo-scale volumes only) | FACT |
| Migration database | `mmp_rt_billing` — the only allowed write target (`allowed_targets.json`) | FACT |
| Migration cluster credential | secret `MONGODB_MMP_RT_TARGET_URI` (user scoped readWrite@mmp_rt_billing). `MONGODB_ATLAS_URI` is NOT used. | FACT |
| Driver language | Python (`pymongo`; harness venv `~/.venvs/recon`) | PROPOSED |
| Repo for migrated code + docs | `Cognition-Partner-Workshops/otterworks`, run branch `tp-run/mongodb-20260926T164927Z-rt-live` (from `origin/tech-partnerships`) | FACT |

## 3. Access
| Field | Value | Kind |
|---|---|---|
| Source credential, first attempt | `ORACLE_BILLING_DSN` (application owner `ow_billing`) — customer hand-over #1 | FACT |
| Source credential, read-only | `ORACLE_BILLING_RO_DSN` (`ow_billing_ro`: CREATE SESSION + SELECT on OW_BILLING tables; provisioned by the customer DBA pre-engagement) | FACT |
| Network path | local container on this VM; no allowlist/VPN; unreachable from any other machine | FACT |
| Security reviewer | none named | PROPOSED |
| Redaction salt | `RECON_REDACT_SALT` unset; harness redacts unsalted | DISCOVERED |

## 4. Correctness contract (`02_tolerances.md`)
| Field | Value | Kind |
|---|---|---|
| Connectivity policy | `online` (both sides probed; any failure blocks; no fallback) | FACT |
| source_access / target_access | recorded in `08_connectivity.json` at STOP A | DISCOVERED |
| Tolerances | exact | FACT |
| Row-diff threshold | 100000 | FACT |
| Source concurrency | 1 | FACT |

## 5. Process
| Field | Value | Kind |
|---|---|---|
| Stop routing | this web session only | FACT |
| `stop_mode` | `soft` for STOP A; **`hard` for STOP B**; STOP C hard (always) | FACT |
| Notification rule | only STOP A/B/C, wave close, halt | FACT |
| PR reviewer | none | FACT |
| Fan-out width | 3 | FACT |
| Cutover principal holder | customer DBA (not present) | FACT |
| Rollback owner | customer DBA (not present) | FACT |
| Merge authority | waves run in soft mode -> `auto_merge: true` (PASS unit PRs merge into the run branch); only live recon against the migration cluster is merge evidence | FACT |

## Resolved access axes (STOP A)
- source_access: live
- target_access: migration_cluster
