# 06_decisions.md — decision log (provenance + blast radius)

| ID | Date | Decision | Forced by (unit / evidence) | Argued in | Invalidates | Owner | Status |
|---|---|---|---|---|---|---|---|
| D-001 | 2026-09-01 | Target catalog is `ow_tp.{bronze,silver,gold}`; runbook's `otterworks.custbill_*` naming is superseded | contracts README + shared-workspace prefix rule | setup (this file) | runbook-databricks.md Beat 2 table (doc only) | parent | PROPOSED → STOP A |
| D-002 | 2026-09-01 | One PR per unit into the run branch; contracts README §"stacked PR series" superseded | org policy from measured rehearsal (knowledge note) | setup | contracts/README.md L38-43 (to be amended in wave 0) | user | PROPOSED → STOP A |
| D-003 | 2026-09-01 | Recon mode LIVE dual-run against regenerated deterministic legacy outputs; no federation | no legacy DB engine exists | 03_recon_tolerances.md | – | user | PROPOSED → STOP A |
| D-004 | 2026-09-01 | Children fixture-first (`run_mode: fixture`), one parent live window per wave on NS=demo | orchestration policy (knowledge note) | 01_conventions.md | – | user | PROPOSED → STOP A |
| D-005 | 2026-09-01 | Scheduler workstream in-house (system cron only, no enterprise scheduler); D5 entries closed by Workflows at cutover | crontab inspection | 00_context.md §3 | – | parent | FACT |
| D-006 | 2026-09-01 | No source-dialect skill exists; `cron-shell-perl-python` dialect notes are wave-0 parent work | skills catalog | 00_context.md §5 | – | parent | FACT |
| D-007 | 2026-09-01 | SQL and ML-SCORING profiles N/A | estate has no SQL objects or models | target_state.md | – | parent | FACT |
