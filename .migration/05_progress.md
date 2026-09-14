# Progress ledger

Status flow: NOT_STARTED -> IN_FLIGHT -> PR_OPEN -> RECON_GREEN -> MERGED (or BLOCKED / FAILED:<class>).

## Stops

| Stop | State | When | Provenance |
|---|---|---|---|
| A | APPROVED | 2026-09-14 | `!dbx_migrate_pipeline` invoked in the orchestrator session after setup; APPROVED (amended: CDC coexistence primary) |
| B | POSTED | 2026-09-14 | inventory complete: `docs/migration/OW_BILLING_inventory.md`, `.migration/08_governance_inventory.md`, `.migration/stops/STOP_B.md`; awaiting pipeline selection (soft stop, default = P1 Monthly invoicing) |
| C | not started | | |
| D | per wave | | |
| E | not started | | |

## Units (pipeline 1)

| Unit | Track | Wave | Status | Money parity | Quarantine rate | Unverified paths | PR | Cost so far (ACU / wh-h) |
|---|---|---|---|---|---|---|---|---|
| (populated by `!dbx_pipeline_analysis`) | | | | | | | | |
