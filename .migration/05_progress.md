# 05 — Progress ledger

Status flow: NOT_STARTED → IN_FLIGHT → PR_OPEN → RECON_GREEN → MERGED. One row per unit; this table is also the cutover-readiness view.

## Chain status
| Step | Status | Artifact / link |
|---|---|---|
| Intake | DONE | `.migration/00_intake_template.md` (PR #1413) |
| Setup (Phase 1 + 2) | DONE, awaiting STOP A | `.migration/` this PR |
| STOP A | APPROVED 2026-09-01 (in-thread reply) | `#ow-migrations` thread |
| Inventory | DONE | `.migration/COMMISSION_DW_inventory.md`, `08_governance_inventory.md` |
| STOP B | APPROVED 2026-09-01 — P1 (whole `COMMISSION_DW` schema), boundary confirmed | `#ow-migrations` thread |
| Analysis + plan / STOP C | DONE; STOP C APPROVED 2026-09-01 (engagement lead, relayed) | `.migration/COMMISSION_DW_analysis.md`, `COMMISSION_DW_plan.md` |
| Wave 0 | IN_FLIGHT | branch `migrate/commission-dw/w0-scaffolding` |
| Waves 1..N | NOT_STARTED | |
| Parallel run | NOT_STARTED | |
| STOP E | NOT_STARTED | |

## Units (filled by analysis; candidate list from intake)
| Wave | Unit | Status | Money parity | Quarantine rate | Unverified paths | PR | Cost so far (ACU / warehouse-min) |
|---|---|---|---|---|---|---|---|
| 0 | W0 scaffolding (catalog, snapshots, skill stub, recon harness, preflight) | NOT_STARTED | – | – | – | – | – |
| 1 (B1-1) | U1 dim_agent | NOT_STARTED | – | – | – | – | – |
| 1 (B1-2) | U2 dim_product | NOT_STARTED | – | – | – | – | – |
| 1 (B1-3) | U3 dim_period | NOT_STARTED | – | – | – | – | – |
| 2 (B2-1) | U4 fact_commission + job load_commission_facts | NOT_STARTED | – | – | – | – | – |
| 2 (B2-1) | U5 mv_agent_commission_summary | NOT_STARTED | – | – | – | – | – |

## Write-target ledger (register BEFORE loading; duplicate = collision → halt)
| Target object | Owning unit | Wave | Registered |
|---|---|---|---|
