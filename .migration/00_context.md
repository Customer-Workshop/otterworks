# 00_context: engagement facts

Intake source: the `!mongo_migrate` kickoff message in Devin session
`983733d4647d4ea2b1fd4344adfa7b65` (2026-09-26). Every row below is FACT (from intake)
unless marked DISCOVERED or PROPOSED.

## Source
| Field | Value | Provenance |
|---|---|---|
| Source family | `oracle` | FACT |
| System + version | Oracle Database Free 23, schema `OW_BILLING`, PDB `FREEPDB1` | FACT |
| DDL location | `services/legacy-billing/db/oracle/schema/*.sql`; PL/SQL under `services/legacy-billing/db/oracle/packages/*.sql` | FACT |
| Headline size | ~10 tables incl. `CUSTOMER_MASTER` (155 cols), `INVOICE_HEADER`, `INVOICE_LINE`, `ENTITY_ATTR_VALUE`, `TENANTS`; 5 PL/SQL packages; demo scale ~200k rows | FACT |
| Other readers/writers | PL/SQL packages + `DBMS_SCHEDULER` jobs in `schema/04_jobs.sql`; billing-service app code under `services/legacy-billing/` | FACT |
| Application code | `services/legacy-billing/app/` (Python, `backends/oracle.py`), `services/legacy-billing/bridge/` | DISCOVERED (tree listing) |

## Target
| Field | Value | Provenance |
|---|---|---|
| Target | local `mongo:7` container only (`MONGO_LOCAL_URI=mongodb://localhost:27017`); no Atlas project or cluster | FACT |
| Migration database | `ow_billing_migration` (the only entry in `allowed_targets.json`) | FACT |
| Driver language | Python (`pymongo`), matching the app | PROPOSED |
| Repo for migrated code + docs | `Cognition-Partner-Workshops/otterworks`, run branch `tp-run/mongodb-20260926T164803Z-rt-offline` (cut from `origin/tech-partnerships`) | FACT |

## Access and connectivity
| Field | Value | Provenance |
|---|---|---|
| Connectivity policy | `offline` | FACT |
| `source_access` | `ddl_only` (reason `policy_offline`) | probe → `08_connectivity.json` |
| `target_access` | `local` (reason `policy_offline`) | probe → `08_connectivity.json` |
| Source read-only credential | none; no source connectivity exists | FACT |
| Migration cluster credential | none. The org environment injects `MONGODB_ATLAS_URI`; the offline guard requires it masked, so every offline command runs as `env -u MONGODB_ATLAS_URI <command>` | DISCOVERED (offline_guard) |
| Network path | n/a | FACT |
| Fixture | same-engine synthetic Oracle Free container `otterworks-oracle-billing-oracle-billing-1` (host port 52521), seeded `NS=demo`; DSN env name `OW_BILLING_FIXTURE_DSN` (demo constant, not a secret); manifest `.migration/fixtures/ow_billing_demo.json`; local target `ow-mongo` (mongo:7, `MONGO_LOCAL_URI`) | DISCOVERED (playbook 2) |
| Can children reach the source? | No. All recon is `--mode fixture --target-class local` (local Oracle Free fixture container + local mongo). It is never merge evidence | FACT |

## Correctness contract
See `02_tolerances.md` / `02_tolerances.json` (version `tol-2` since D-011; STOP A accepted `tol-1`): exact tolerances,
row-diff threshold 100000, source concurrency 1.

## Process
| Field | Value | Provenance |
|---|---|---|
| Stop routing | this web session only | FACT |
| `stop_mode` | `soft` (60 s default-accept) for STOP A and STOP B; STOP C hard (always) | FACT |
| Merge authority | `auto_merge: false` in every wave manifest and for every orchestrator-owned PR. Offline/local evidence is never merge evidence (AGENTS.md rule 11); this overrides the soft-mode `auto_merge: true` default. No PR is merged in this engagement | FACT |
| PR reviewer | none; self-verify only | FACT |
| Fan-out width | 3 | FACT |
| Cutover principal holder | customer DBA (not present) | FACT |
| Rollback owner | customer DBA (not present) | FACT |
| Notification contract | STOP A/B/C, wave close, halt: one message each, in this session, exceptions first | FACT |
