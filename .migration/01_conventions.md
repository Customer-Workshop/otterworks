# Working conventions

## Branches and PRs
- Run branch: `tp-run/databricks-20260914T183234Z`. Every unit PR targets it. Never `tech-partnerships`, never `main`.
- Child branch naming: `migrate/p1/<wave>-<unit>` (e.g. `migrate/p1/w1-invoicing`). One PR per unit.
- PR body: what the unit converts, its write targets, the recon verdict line, a link to the committed `*.recon.json`. No requester names or emails; a session link is fine.
- Every unit PR carries its own machine-readable recon output under `.migration/units/<unit>/recon/` (`"kind": "recon-report"`, `*.recon.json`, validated against `docs/tech-partnerships/contracts/schema/recon-report.schema.json`). Prose is not evidence.
- `make tp-smoke` must pass on every PR.
- Merge authority: `stop_mode: soft` -> `auto_merge: true` for PASS PRs verified by the independent recon session. A safety halt (write-target anomaly) holds merges regardless.

## Ledger discipline
- `.migration/` is written only by the orchestrator (this session) and the fan-out workflow. Children write only `.migration/units/<unit>/` inside their own PR and never touch the shared files.
- `allowed_targets.json` and `03_recon_tolerances.json` change only through a `06_decisions.md` row plus a commit.
- `09_capabilities.json` is doctor output, never hand-edited.

## Naming (target)
- Unity Catalog: `ow_tp.<schema>.<legacy_name_lowercase>`; per-batch isolation `ow_tp.<schema>__p1w<N>_<unit>` for Delta staging.
- Lakebase: schema `ow_billing` inside db `databricks_postgres` on branch `mig-p1-w<N>-<batch>` (TTL 72 h, dropped at wave close). Legacy table and column names preserved (lowercased, Postgres-quoted only where reserved). Forced renames go in the unit mapping.
- Jobs/pipelines: `ow_tp_<unit>`, `ns=demo` parameter, PAUSED schedules until STOP E.
- Volumes: `/Volumes/ow_tp/bronze/landing/<ns>/<unit>/...`.
- Debezium/Kafka topics: `ow_tp.ow_billing.<table>`.

## Secrets
- Reference by name only: `ORACLE_OW_BILLING_RO_DSN` (AWS SM `ow-tp/oracle/ow_billing_ro`), `DATABRICKS_DEMO_HOST`, `DATABRICKS_DEMO_TOKEN`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, `LAKEBASE_OW_TP_BILLING_DSN` (derived at runtime, 1 h). Never printed, never committed.

## Source access rules
- Oracle: SELECT only, `SET TRANSACTION READ ONLY` / `AS OF SCN` for pins, no `FOR UPDATE`, no `DBMS_*` calls except `DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER`-equivalent reads via `V$DATABASE.CURRENT_SCN`.
- Legacy query cap: 2 concurrent recon queries per unit, 4 total (PROPOSED, STOP A).
- Fixture first: children develop against the seeded fixture copy in their Lakebase branch / Delta staging, then read the live source once inside the cap.

## Recon
- Operational units: `dbx-recon run --mode transactional --target-kind lakebase --tolerances .migration/03_recon_tolerances.json` against the batch branch. Mapping names `watermark` and `identity` per table.
- Analytical units: `dbx-recon run --mode snapshot` at the pinned SCN, `--target-kind databricks`.
- Planted anomalies (37 orphan `INVOICE_LINE` rows, dirty `SIGNUP_DT`, malformed CSV lists) are compared as sets and landed in `ow_tp.ops.quarantine_<unit>`, never dropped.

## Messaging
- One message per event (stop, wave close, halt). 2-4 sentences, decision first, recommendation, exact approving reply, artifact links.
