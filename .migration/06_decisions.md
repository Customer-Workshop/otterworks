# 06_decisions.md — decision log (provenance + blast radius)

| ID | Date | Decision | Forced by (unit / evidence) | Argued in | Invalidates | Owner | Status |
|---|---|---|---|---|---|---|---|
| D-001 | 2026-09-01 | Target catalog is `ow_tp.{bronze,silver,gold}`; runbook's `otterworks.custbill_*` naming is superseded | contracts README + shared-workspace prefix rule | setup (this file) | runbook-databricks.md Beat 2 table (doc only) | parent | APPROVED at STOP A 2026-09-01 (https://cogpartners.slack.com/archives/C0BQP3P965V/p1788296591998709) |
| D-002 | 2026-09-01 | One PR per unit into the run branch; contracts README §"stacked PR series" superseded | org policy from measured rehearsal (knowledge note) | setup | contracts/README.md L38-43 (to be amended in wave 0) | user | APPROVED at STOP A 2026-09-01 (https://cogpartners.slack.com/archives/C0BQP3P965V/p1788296591998709) |
| D-003 | 2026-09-01 | Recon mode LIVE dual-run against regenerated deterministic legacy outputs; no federation | no legacy DB engine exists | 03_recon_tolerances.md | – | user | APPROVED at STOP A 2026-09-01 (https://cogpartners.slack.com/archives/C0BQP3P965V/p1788296591998709) |
| D-004 | 2026-09-01 | Children fixture-first (`run_mode: fixture`), one parent live window per wave on NS=demo | orchestration policy (knowledge note) | 01_conventions.md | – | user | APPROVED at STOP A 2026-09-01 (https://cogpartners.slack.com/archives/C0BQP3P965V/p1788296591998709) |
| D-005 | 2026-09-01 | Scheduler workstream in-house (system cron only, no enterprise scheduler); D5 entries closed by Workflows at cutover | crontab inspection | 00_context.md §3 | – | parent | FACT |
| D-006 | 2026-09-01 | No source-dialect skill exists; `cron-shell-perl-python` dialect notes are wave-0 parent work | skills catalog | 00_context.md §5 | – | parent | FACT |
| D-007 | 2026-09-01 | SQL and ML-SCORING profiles N/A | estate has no SQL objects or models | target_state.md | – | parent | FACT |
| D-008 | 2026-09-01 | Estate partition P-A {J1,J5}, P-B {J6,J7,J8,J9}, P-C {J2}, P-D {J4}, P-E {J3}; coverage 20 = 9 + 11 shared + 0 unused + 0 excluded | inventory census | OtterWorks_ETL_inventory.md §3-4 | 05_progress wave proposal (J5 was in pilot with P-B; inventory shows J5 depends on J1, not on P-B) | user | PROPOSED → STOP B |
| D-009 | 2026-09-01 | D4-2 (admin-service reads user-activity report) is INFERRED, not FACT — no reader in `services/` | repo grep | 04_dependency_register D4-2 | 00_context.md §2 row 5 wording | customer | OPEN → confirm at STOP B/C |
| D-010 | 2026-09-01 | Nothing PROPOSED-unused; `etl/crontab` redundancy and dead sendmail branch flagged only | no run evidence in scope | inventory §4 | – | user | PROPOSED → STOP B |
