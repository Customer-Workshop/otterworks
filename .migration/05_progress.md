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
| Wave 0 | MERGED (PR #1422, CI green, 6 review findings fixed) — all 6 gates green (catalog+schemas+volume, preflight 11/11 probes 0 denied, legacy load FACT 0→3, 9-object baseline hash-pinned, Files API landing checksum 0 mismatches, 4 bronze feed tables loaded, skill stub, harness validated) | branch `migrate/commission-dw/w0-scaffolding`; evidence `.migration/COMMISSION_DW_wave0_evidence.md` |
| Waves 1..N | Wave 1 MERGED 2026-09-01 (#1425 #1426 #1427; independent recon PASS ×3); wave 2 IN_FLIGHT 2026-09-01 (B2-1 child f06d0fb2, width 1) | ledger PR #1424 |
| Parallel run | NOT_STARTED | |
| STOP E | NOT_STARTED | |

## Units (filled by analysis; candidate list from intake)
| Wave | Unit | Status | Money parity | Quarantine rate | Unverified paths | PR | Cost so far (ACU / warehouse-min) |
|---|---|---|---|---|---|---|---|
| 0 | W0 scaffolding (catalog, snapshots, skill stub, recon harness, preflight) | MERGED | n/a | n/a | none | #1422 | parent session; warehouse ≈2 min |
| 1 (B1-1) | U1 dim_agent | MERGED | n/a | 0 | live-legacy-comparison (DEGRADED) | #1426 | ≈5.0 ACU / ≤15 wh-min |
| 1 (B1-2) | U2 dim_product | MERGED | n/a | 0 | live-legacy-comparison (DEGRADED) | #1425 | ≈4.6 ACU / ≈2 wh-min |
| 1 (B1-3) | U3 dim_period | MERGED | n/a | 0 | live-legacy-comparison (DEGRADED) | #1427 | ≈3.5 ACU / ≈8 wh-min |
| 2 (B2-1) | U4 fact_commission + job load_commission_facts | IN_FLIGHT | – | – | – | – | – |
| 2 (B2-1) | U5 mv_agent_commission_summary | IN_FLIGHT | – | – | – | – | – |

## Write-target ledger (register BEFORE loading; duplicate = collision → halt)
| Target object | Owning unit | Wave | Registered |
|---|---|---|---|
| `ow_tp` catalog, schemas `bronze`/`silver`/`gold`/`ops`, volume `ow_tp.bronze.landing` | W0 (parent) | 0 | 2026-09-01 |
| `/Volumes/ow_tp/bronze/landing/cdw/{feed,baseline}/*` | W0 (parent) | 0 | 2026-09-01 |
| `ow_tp.bronze.agents_cdw`, `products_cdw`, `policies_cdw`, `commission_ledger_cdw` | W0 (parent); refreshed only by U4 job task T0 | 0 | 2026-09-01 |
| `ow_tp.silver.dim_agent_cdw` | U1 | 1 | 2026-09-01 (registered by parent at W1 launch) |
| `ow_tp.silver.dim_product_cdw` | U2 | 1 | 2026-09-01 (registered by parent at W1 launch) |
| `ow_tp.silver.dim_period_cdw` | U3 | 1 | 2026-09-01 (registered by parent at W1 launch) |
| `ow_tp.silver.fact_commission_cdw`, `ow_tp.ops.run_log_cdw`, `ow_tp.ops.quarantine_cdw`, job `ow_tp_cdw_load_commission_facts`, notebooks `/Shared/ow_tp/cdw/*` | U4 | 2 | 2026-09-01 (registered by parent at W2 launch) |
| `ow_tp.gold.mv_agent_commission_summary_cdw` | U5 | 2 | 2026-09-01 (registered by parent at W2 launch) |
