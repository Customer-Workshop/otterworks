# 05_progress.md — ledger (one row per unit; also the cutover-readiness view)

Status flow: NOT_STARTED → IN_FLIGHT → PR_OPEN → RECON_GREEN → MERGED. Write targets must be
registered here before any load; a collision halts the wave.

| # | Unit | Wave | Status | Write targets (registered) | Money parity | Quarantine rate | Unverified paths | PR | Cost so far (ACU / wh-h) |
|---|---|---|---|---|---|---|---|---|---|
| 0 | shared objects (catalog, schemas, volume, scope, dbx.py, contracts, dialect notes) | 0 | NOT_STARTED | `ow_tp`, `ow_tp.{bronze,silver,gold}`, `/Volumes/ow_tp/bronze/landing`, scope `ow_tp` | – | – | – | – | – |
| 6 | sftp_ingest_poll.ksh | 1 (pilot) | NOT_STARTED | – | – | – | – | – | – |
| 7 | parse_custbill_fixedwidth.sh | 1 (pilot) | NOT_STARTED | – | – | – | – | – | – |
| 8 | finance_excel_report.pl | 1 (pilot) | NOT_STARTED | – | – | – | – | – | – |
| 5 | user_activity_daily.py | 1 (pilot) | NOT_STARTED | – | – | – | – | – | – |
| 1 | analytics_daily.py | 2 | NOT_STARTED | – | – | – | – | – | – |
| 2 | audit_archive_weekly.py | 2 | NOT_STARTED | – | – | – | – | – | – |
| 3 | search_reindex_weekly.py | 2 | NOT_STARTED | – | – | – | – | – | – |
| 4 | storage_cleanup_daily.py | 2 | NOT_STARTED | – | – | – | – | – | – |
| 9 | run_all.sh + estate rollup / Workflow | 3 | NOT_STARTED | – | – | – | – | – | – |

Wave assignment above is the front-door PROPOSAL; `!dbx_pipeline_analysis` / `!dbx_migration_plan`
finalise it at STOP C. Inventory (`docs/tech-partnerships/OtterWorks_ETL_inventory.md`) partitions the
estate into P-A {1,5}, P-B {6,7,8,9}, P-C {2}, P-D {4}, P-E {3}; max width 5, serial floor 3 (P-B).

## Phases
| Phase | Status | Date | Evidence |
|---|---|---|---|
| setup | DONE | 2026-09-01 | commits `49c2fe7c`, `d1e1f790` |
| inventory | DONE, STOP B posted | 2026-09-01 | `OtterWorks_ETL_inventory.md`, `OtterWorks_ETL_dag.png`, `08_governance_inventory.md`; coverage 20 = 9 + 11 + 0 + 0 |

## Stops
| Stop | Status | Date | Evidence |
|---|---|---|---|
| A | APPROVED ("approved", dhrov.subramanian) | 2026-09-01 | https://cogpartners.slack.com/archives/C0BQP3P965V/p1788296591998709 |
| B | POSTED, awaiting pipeline choice | 2026-09-01 | (thread permalink filled after post) |
| C | – | | |
| D (per wave) | – | | |
| E | – | | |
