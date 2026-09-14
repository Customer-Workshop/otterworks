# Progress ledger

Status flow: NOT_STARTED -> IN_FLIGHT -> PR_OPEN -> RECON_GREEN -> MERGED (or BLOCKED / FAILED:<class>).

## Stops

| Stop | State | When | Provenance |
|---|---|---|---|
| A | APPROVED | 2026-09-14 | `!dbx_migrate_pipeline` invoked in the orchestrator session after setup; APPROVED (amended: CDC coexistence primary) |
| B | APPROVED | 2026-09-14 | inventory complete: `docs/migration/OW_BILLING_inventory.md`, `.migration/08_governance_inventory.md`, `.migration/stops/STOP_B.md`; awaiting pipeline selection (soft stop, default = P1 Monthly invoicing) |
| C | APPROVED (DEC-C/C1); HALT before wave 0 on D10-7b (DEC-C2) | 2026-09-14 | `docs/migration/P1_monthly_invoicing_analysis.md`, `P1_monthly_invoicing_plan.md`, `.migration/waves/wave-{0,1,2}.json`, `.migration/stops/STOP_C.md` |
| D | per wave | | |
| E | not started | | |

## Units (pipeline 1)

| Unit | Track | Wave | Status | Money parity | Quarantine rate | Unverified paths | PR | Cost so far (ACU / wh-h) |
|---|---|---|---|---|---|---|---|---|
| U0 shared-core (`CODES`, `PLANS`, `TENANTS`, `BILLING_AUDIT_LOG`, `PKG_OW_UTIL`) | operational (+Delta copies) | 0 | NOT_STARTED | | | | | |
| U1 plans-subscriptions (`SUBSCRIPTIONS`, `SUBSCRIPTIONS_HIST`, `PKG_PLANS`, 2 triggers) | operational (+Delta copy of hist) | 1 | NOT_STARTED | | | | | |
| U2 usage-events (`USAGE_EVENTS`, check trigger, ingest surface) | operational | 1 | NOT_STARTED | | | | | |
| U3 rating (`RATING_PERIODS`, `RATING_RESULTS`, `PKG_RATING`) | operational | 2 | NOT_STARTED | | | | | |
| U4 invoicing-credits (`INVOICES`, `INVOICE_LINES`, `CREDIT_NOTES`, `PKG_INVOICING`) | operational | 3 | NOT_STARTED | | | | | |
