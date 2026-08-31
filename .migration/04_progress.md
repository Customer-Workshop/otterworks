# 04 — Progress ledger

## Write-target registry

Every write target is registered here **before** any load runs. A second unit claiming a
registered target is a collision: halt immediately, do not load, escalate.

| Target namespace | Owning unit | Registered at | Load status |
|---|---|---|---|
| `ow_tp_demo.customers` | `customers` | STOP A | not loaded |
| `ow_tp_demo.invoices` | `invoices` | STOP A | not loaded |
| `ow_tp_demo_quarantine.customers` | `customers` | STOP A | not loaded |
| `ow_tp_demo_quarantine.invoices` | `invoices` | STOP A | not loaded |

Registered and already released: `ow_tp_demo._migration_preflight` (STOP A capability
probe; document inserted, read, deleted, collection dropped — no residue).

Explicitly **not** owned by this engagement, on the same cluster:
`ow_tp_billing_demo`, `ow_tp_demo1`, `ow_tp_mongodb_demo`, `ow_tp_mongodb_demo_quarantine`.
A write to any of them is a guardrail breach, not a collision to negotiate.

## Unit / wave ledger

| Wave | Unit | Mapping version | Tolerance version | Recon verdict | PR | Status |
|---|---|---|---|---|---|---|
| 1 | `customers` | — | 1 | — | — | not started |
| 2 | `invoices` | — | 1 | — | — | not started |

A unit is **done** only when its PR is merged into `tp-run/mongodb-20260831T232410Z` with a
green harness verdict recorded above. "Code written" and "recon run locally" are not done.

Declared coverage gaps (no unit will ingest these; see `00_context.md`): the Postgres
`documents` workload, the DynamoDB `files` workload, and the 16 `OW_BILLING` tables outside
the two units.

## Circuit-breaker log

Rule: 3 same-class failures across units halts the wave and escalates. Retrying past the
third is a breach.

| # | Date | Unit | Failure class | Action |
|---|---|---|---|---|
| — | — | — | — | no failures recorded |
