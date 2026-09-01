# 05 — Progress ledger

Status flow: NOT_STARTED → IN_FLIGHT → PR_OPEN → RECON_GREEN → MERGED. One row per unit; this table is also the cutover-readiness view.

## Chain status
| Step | Status | Artifact / link |
|---|---|---|
| Intake | DONE | `.migration/00_intake_template.md` (PR #1413) |
| Setup (Phase 1 + 2) | DONE, awaiting STOP A | `.migration/` this PR |
| STOP A | APPROVED 2026-09-01 (in-thread reply) | `#ow-migrations` thread |
| Inventory / STOP B | NOT_STARTED | |
| Analysis + plan / STOP C | NOT_STARTED | |
| Wave 0 | NOT_STARTED | |
| Waves 1..N | NOT_STARTED | |
| Parallel run | NOT_STARTED | |
| STOP E | NOT_STARTED | |

## Units (filled by analysis; candidate list from intake)
| Wave | Unit | Status | Money parity | Quarantine rate | Unverified paths | PR | Cost so far (ACU / warehouse-min) |
|---|---|---|---|---|---|---|---|
| – | dim_agent | NOT_STARTED | – | – | – | – | – |
| – | dim_product | NOT_STARTED | – | – | – | – | – |
| – | dim_period | NOT_STARTED | – | – | – | – | – |
| – | fact_commission | NOT_STARTED | – | – | – | – | – |
| – | load_commission_facts (DW_ETL_PKG) | NOT_STARTED | – | – | – | – | – |
| – | mv_agent_commission_summary | NOT_STARTED | – | – | – | – | – |

## Write-target ledger (register BEFORE loading; duplicate = collision → halt)
| Target object | Owning unit | Wave | Registered |
|---|---|---|---|
