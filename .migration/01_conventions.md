# 01 — Working conventions

| Topic | Convention |
|---|---|
| Run branch | `tp-run/databricks-20260901T205306Z`. Never PR into `main` or `tech-partnerships`. |
| Unit branches | `migrate/commission-dw/<wave>-<unit>` (e.g. `migrate/commission-dw/w1-dim_agent`), cut from the run branch. |
| PRs | One PR per unit, never stacked; target = run branch; title `[CDW w<N>] <unit>: <what>`; body = summary, contract link, `recon.summary.md` rendered, link to `<unit>.recon.json`; no requester name/email. `tp-pre-pr-self-check` before opening; `make tp-smoke`, `make tp-validate-recon FILE=…` green. 2 review rounds budget. |
| Definition of done | PR **merged** into the run branch with recon PASS. |
| Namespace | `cdw`. Every Databricks object `ow_tp.<schema>.<object>_cdw`; volume path `/Volumes/ow_tp/bronze/landing/cdw/<unit>/`; jobs `ow_tp_cdw_<unit>`; notebooks `/Shared/ow_tp/cdw/`. |
| Code layout | `dbx/commission_dw/<unit>/` — `ddl.sql`, `load.sql` (or notebook), `recon/<unit>.recon.json`, `recon/recon.summary.md`, `contract.md`. Contracts also indexed from `docs/tech-partnerships/contracts/README.md`. |
| Snapshots | `etl/legacy-extra/commission_dw/<ns>/` holds extract CSVs + `manifest.json`; landed with `FIXTURE_SOURCE=etl/legacy-extra/commission_dw/<ns> make tp-fixture-land NS=<ns>`; `make tp-fixture-verify NS=<ns>`. |
| Recon evidence | `run_mode: fixture` for child iterations; the parent's single uncontended pass is the only `live` proof; header carries recon mode DEGRADED + tolerance record version. |
| Write-target registration | before any load, a child appends its write targets to `05_progress.md` (Write-target ledger); a duplicate = collision → halt, post `#ow-tp-alerts`. |
| Legacy access | read-only, as `commission_dw`, `sqlplus -S` inside the fixture container; ≤ 2 concurrent sessions. |
| Secrets | by name only (`DATABRICKS_DEMO_HOST`, `DATABRICKS_DEMO_TOKEN`). |
| Determinism | legacy runs and baseline extraction via `scripts/tp-run-deterministic.sh` (`TZ=UTC LC_ALL=C`); gzip `mtime=0`; no embedded timestamps except in manifests. |
| Ledger discipline | `04_dependency_register.md`, `05_progress.md`, `06_decisions.md` updated after every step; later playbooks append, never rewrite. |
