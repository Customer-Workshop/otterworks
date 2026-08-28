# 00 — Migration context

## Engagement boundary

| Field | Status and value |
|---|---|
| Estate | **FACT** — `OW_BILLING` only for this run (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:153-154`). |
| Excluded estate | **FACT** — `COMMISSION_DW` is out of scope, not a deferred unit in this run (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:153-154`). |
| Oracle engine | **FACT** — Oracle AI Database 26ai Free, full version `23.26.3.0.0` (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:15-18`). |
| PDB and schema | **FACT** — PDB `FREEPDB1`, schema `OW_BILLING` (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:15-19`). |
| Connection | **FACT** — host port `52521`, container port `1521`, service `FREEPDB1` (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:18-20`). |
| Container | **FACT** — `otterworks-oracle-billing-oracle-billing-1` (live setup probe, recorded in `07_access_checklist.md`). |

## Repository roles

- **FACT — SOURCE:** `services/legacy-billing/db/oracle` and `etl/legacy-extra` contain the legacy schema, packages, scheduler, and batch/report sources (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:81-87`; `services/legacy-billing/db/oracle/README.md:40-49`).
- **FACT — TARGET:** this repo's `databricks/` and `infrastructure/terraform-databricks/` hold target notebooks, SQL/DDL, and per-unit job definitions (`docs/tech-partnerships/contracts/README.md:19-22`; `origin/tech-partnerships-solutions:infrastructure/terraform-databricks/README.md:1-8`).
- **FACT — DOCS:** `docs/tech-partnerships/` holds contracts, runbooks, intake, target state, and recon evidence (`docs/tech-partnerships/contracts/README.md:1-11`).
- **FACT — reference note:** the current run branch does not carry the merged target helper/stack; `origin/tech-partnerships-solutions` is reference-only. The live probe used that branch's `scripts/tp_databricks/dbx.py` without adding it to this setup commit.

## Branch topology

- **FACT:** each run starts from a fresh `tp-run/*` branch; migration work never targets `tech-partnerships` or `main` (`docs/tech-partnerships/contracts/README.md:38-43`).
- **FACT:** child units use `migrate/ow_billing/<wave>-<unit>` and one PR per unit (`docs/tech-partnerships/contracts/README.md:38-43`).
- **FACT:** branches contain code only: no data, state, or secrets (`docs/tech-partnerships/contracts/README.md:27-29`).

## Settled migration posture

- **FACT:** target state is documented in `docs/tech-partnerships/OW_BILLING_target_state.md`; the settled intake is `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md`.
- **FACT:** coexistence is federation-first over JDBC, customer-approved, with recon mode `LIVE` (`docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:138-145,153-154`).
- **FACT:** authored tolerances are the parity contract in `.migration/03_recon_tolerances.md`; do not re-derive them.

## Notification contract

**FACT:** send only to Slack `#ow-migrations` (channel `C0BQP3P965V`):

1. blocking STOP A, B, C, or E when artifacts are ready;
2. STOP D wave close with exception count; and
3. any fan-out halt caused by a write-target collision or tripped circuit breaker.

Send nothing else. The authoritative answer is always taken from the originating web
session. A channel that receives every green PR gets muted; then the halts get missed.
