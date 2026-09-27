# 01 — Conventions (run 20260927c)

## Naming

| Thing | Pattern | Example |
|---|---|---|
| Run branch (PR base) | `tp-run/databricks-<UTC stamp>` | `tp-run/databricks-20260927T194945Z` |
| Unit branch | `mig/20260927c/<unit-id>` | `mig/20260927c/w1-pkg-plans` |
| Unit id | `w<wave><letter>-<slug>` | `w0a-pkg-ow-util`, `w2a-custbill-pipeline` |
| PR title | `mig(<unit-id>): <what moved>` | `mig(w1b-pkg-rating): pkg_rating -> billing.fn_usage_rating/sp_finalize_rating` |
| Lakebase branch | `mig-20260927c-w<n>` (one per wave, TTL 7d); `mig-20260927c-exec` (routine-parity exec, TTL 7d) | `mig-20260927c-w1` |
| Lakebase schema | `billing` (matches `services/legacy-billing/app/backends/postgres.py`) | `billing.sp_issue_invoice` |
| UC schema | `ow_tp.mig_20260927c_<layer>` | `ow_tp.mig_20260927c_gold` |
| UC volume | `ow_tp.mig_20260927c_bronze.landing` | CUSTBILL `.dat` drop |
| Pipeline / job / dashboard | `ow_tp_20260927c_<slug>` | `ow_tp_20260927c_custbill` |
| Lakebase object | same name as Oracle, lower snake; routines `fn_<name>` (returns rows) / `sp_<name>` (procedure) | `pkg_invoicing.sp_issue_invoice` -> `billing.sp_issue_invoice` |
| Recon artifacts | `.migration/recon/<unit-id>/` (fixture/, live/, routines/) | |
| Unit specs | `.migration/units/<unit-id>/{mapping_spec.json,cost_estimate.json,ops.json}` | |

## Code and files

- Converted SQL lives in `databricks/mig_20260927c/lakebase/<nn>_<object>.sql`; pipeline code in `databricks/mig_20260927c/custbill/`; dashboard JSON in `databricks/mig_20260927c/dashboards/`; bundle `databricks/mig_20260927c/*/databricks.yml` target `mig_20260927c`.
- Lakebase DDL is applied with `psql "$LAKEBASE_MIGRATION_DSN" -v ON_ERROR_STOP=1 -f <file>` (DSN exported from a named secret / `databricks postgres` credential; the hook resolves `$LAKEBASE_MIGRATION_DSN` via `allowed_targets.json`). Never a literal host in a command.
- Type map: Oracle `VARCHAR2(n)` -> `varchar(n)`; `NUMBER(p,s)` -> `numeric(p,s)`; `NUMBER(p,0)` -> `integer`/`bigint`; `DATE` -> `timestamp(0)`; `TIMESTAMP(6)` -> `timestamp(6)` (no zone, D-010); `CHAR(1) Y/N` -> `char(1)` kept (not boolean) so recon is literal. Delta side per `skills/oracle-plsql/canonicalization.json` `type_map.oracle.databricks`.
- Fixture first: children develop against the local Oracle fixture (`make oracle-billing-up`, `:52521/FREEPDB1`, static seed identical for the 9 static tenants) and against a fixture snapshot committed under `testdata/legacy/oracle/mig_20260927c/` (static seed rows only — never EC2 rows). One live read of `52.201.36.9` per child, through `dbx-recon --family oracle` only.
- Legacy source is never modified (no DDL, DML, grants, scheduler changes, no `ALTER DATABASE`); a block by `hooks/dbx_guard.py` is reported, never routed around.
- Secrets by name: `ow-tp/oracle/ow_billing_ro` (AWS SM) -> `OW_BILLING_RO_DSN`; Lakebase credentials via `databricks postgres generate-database-credential` at run time -> `LAKEBASE_MIGRATION_DSN` / `LAKEBASE_EXEC_DSN`; Databricks via `oauth-m2m` env (`DATABRICKS_CLIENT_ID/SECRET`). Nothing is printed or committed.

## PR contract (every unit PR)

1. Base = run branch; unit branch per pattern above; one PR per unit batch.
2. Body: unit id, wave, source objects, target objects, declared write targets (must equal the manifest), mapping spec path, recon report path + verdict line (`dbx-recon ... verdict=PASS mode=live`), known deviations with decision ids.
3. `make tp-smoke` and the unit checks from `.agents/skills/tp-pre-pr-self-check` pass before opening.
4. Merge only when the `dbx-recon` verdict is PASS in live/snapshot mode and the wave's independent verifier agrees; merges are performed by the orchestrator after the wave-close notice, never by a child.
5. No production rows in the PR (fixture snapshot rows are static-seed only; live recon artifacts are redacted by the harness).

## Schedules and cutover

- Every Lakeflow job/pipeline lands `pause_status: PAUSED` (`continuous: false`); children run them once by hand with `--full-refresh` on migration targets only.
- No consumer repoint, no `BILLING_BACKEND` change on a deployed service, no Lakebase production branch use. The Databricks-flow recording runs the legacy-billing app locally with `BILLING_BACKEND=postgres` against `mig-20260927c-exec`.
