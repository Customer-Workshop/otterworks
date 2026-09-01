# 00 — Engagement context

**Engagement**: OtterWorks Commission Pay data warehouse (`COMMISSION_DW`, Oracle) → Databricks lakehouse.
**Front door**: `!dbx_migrate_warehouse` (intake: `00_intake_template.md`). **Driver**: `!dbx_migrate_pipeline`.
**Target-state artifact**: `.migration/COMMISSION_DW_target_state.md` (v1). Knowledge note: to be created after STOP A confirmation.

## Scope
- IN: schema `COMMISSION_DW` — `DIM_AGENT`, `DIM_PRODUCT`, `DIM_PERIOD`, `FACT_COMMISSION`, `MV_AGENT_COMMISSION_SUMMARY`, package `DW_ETL_PKG`.
- OUT: `COMMISSION_PAY.COMMISSION_PKG` and all `COMMISSION_PAY` OLTP logic. `COMMISSION_PAY.AGENTS/PRODUCTS/POLICIES/COMMISSION_LEDGER` are an upstream feed (D3-1) only.

## Topology
| Role | Where |
|---|---|
| Legacy source | Oracle Database Free 26ai, PDB `FREEPDB1`, brought up with `make insurance-up NS=<ns>`; loopback-only listener. Assessment user `commission_dw` (read-only use only; never DDL/DML) |
| Target | Databricks workspace at secret `DATABRICKS_DEMO_HOST`; token `DATABRICKS_DEMO_TOKEN`; warehouse `565cd2fd713738c4`; catalog `ow_tp` (bronze/silver/gold/ops), namespace `cdw` |
| Repo (SOURCE+TARGET+DOCS) | `Cognition-Partner-Workshops/otterworks`, run branch `tp-run/databricks-20260901T205306Z`; `.migration/` at repo root |
| Federation | not reachable (D10-1) → snapshot coexistence, recon DEGRADED |

## Contacts
| Role | Who |
|---|---|
| Engagement lead / approver | the requester (approves stops in Slack threads) |
| PR reviewer | engagement lead |
| Security reviewer | OPEN → proposed N/A (STOP A) |
| Cutover principal holder | OPEN → customer-held, named at STOP E (STOP A) |

## Interaction contract
- Blocking stops A/B/C/E → Slack `#ow-migrations` (C0BQP3P965V); approvals are in-thread replies.
- Emergency halts (write-target collision, circuit breaker) → `#ow-tp-alerts` (C0BQP3LU3JT).
- Wave closes (STOP D) → `#ow-tp-status` (C0BRYRE5ZQQ), with the wave-close brief and exception count.
- Nothing else pings. No per-child, no per-green-PR posts. Daily digest: off.
- Message style: 2–4 sentences, lead with the decision, state the exact approving reply, link artifacts. Questions one at a time with options.
- Audience-facing surfaces (Slack, PRs, Jira/Confluence) describe the estate as the production legacy system it is; never name or email the requester in PR content.
