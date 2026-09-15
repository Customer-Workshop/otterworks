# 05_progress — the ledger

One row per unit, one section per pipeline. The parent is the only writer here; children
write only under `.migration/recon/`.

Status values: `not started` → `in flight` → `recon PASS` / `recon FAIL` → `merged` →
`parallel run` → `cutover`.

## Run state

| Item | Value |
|---|---|
| Phase | setup complete → STOP A |
| Branch | `tp-run/databricks-20260915T045714Z` |
| Waves closed | 0 |
| Units merged | 0 |
| Open D10s | D10-01 (federation / SG), D10-04 (identity confirmation) |
| Circuit breaker | not tripped |

## Pipeline 1 — monthly invoicing (Oracle → Lakebase + Delta, with CDC)

Units are assigned at STOP C, after the inventory and analysis playbooks run. Not started.

## Pipeline 2 — finance close (CUSTBILL → Lakeflow)

Blocked until pipeline 1 is parked at STOP E. Not started.

## Pipeline 3 — product analytics (Python/Scala → Lakeflow Jobs)

Blocked until pipeline 2 is parked at STOP E. Not started.

## Build sessions (not migration units — no recon gate)

Launch once pipeline 1 has reconciled. Graded on their own acceptance criteria.

| Session | Scope | Status |
|---|---|---|
| B1 | per-tenant usage meter feeding Lakebase | not started |
| B2 | finance gold layer (ARR, MRR by plan, AR ageing, overage, storage cost per tenant) + dashboard | not started |
| B3 | dunning-risk score synced back to Lakebase | not started |

## Setup log

| When | What |
|---|---|
| 2026-09-15 | Intake completed and confirmed; branch cut and pushed |
| 2026-09-15 | `make tp-preflight PLATFORM=databricks`: 11 probes, 0 denied |
| 2026-09-15 | Approved one-time Oracle supplemental-log DDL applied (D-001); archive-log housekeeping installed |
| 2026-09-15 | `.migration/` initialized; recon harness installed, `dbx-recon selftest` PASS |
