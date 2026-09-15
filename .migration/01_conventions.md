# 01_conventions

## Branches and PRs

- Working branch (the only PR base): `tp-run/databricks-20260915T045714Z`.
  `tech-partnerships` is immutable legacy before-state and never receives a migration PR.
- Child branch: `migrate/<pipeline>/<wave>-<unit>`, e.g. `migrate/p1/w1-invoices`.
- One PR per migration unit. Never a stack.
- Every unit PR carries its own recon output (`.migration/recon/<unit>/summary.md` plus the
  `result.json` verdict) in the body. A PR without a live-mode verdict is not merge-eligible.
- PR bodies name no individuals and carry no credentials.

## Naming

| Thing | Pattern | Example |
|---|---|---|
| Catalog / schema | `ow_tp.<bronze\|silver\|gold>` | `ow_tp.silver` |
| Delta table | `<source table lowercased>` | `ow_tp.silver.invoice_lines` |
| CDC history | `<table>_hist` (SCD-2) | `ow_tp.silver.customer_master_hist` |
| Quarantine | `<pipeline>_quarantine` | `ow_tp.bronze.custbill_quarantine` |
| Lakeflow pipeline | `ow_tp_<pipeline>_<purpose>` | `ow_tp_p2_custbill_close` |
| Lakeflow job | `ow_tp_<pipeline>_<purpose>` | `ow_tp_p3_analytics_daily` |
| Lakebase branch | `mig-<pipeline>-<wave>-<batch>` | `mig-p1-w1-b2` |
| Secret scope | `ow_tp` | |
| Unit id | `<pipeline>-<object>` | `p1-invoices` |

## Working rules

- Children write only the namespace slice in their brief, and never touch `.migration/`
  outside `recon/`.
- No DDL on shared tables from a child. Shared objects are wave 0, serial, one owner.
- Fixture first, one live run: develop against the fixture, read the real source once inside
  the granted live window.
- Every schedule lands PAUSED.
- Secrets by name only.
- Repo gates before any PR: `make tp-smoke`, plus the unit's recon verdict.
