# 00_context — engagement facts

Estate: OtterWorks billing (Oracle `OW_BILLING`, CUSTBILL finance close, Python/Scala analytics).
Target: Databricks (`ow_tp`) + Lakebase Postgres (`ow-tp-billing`).
Run branch: `tp-run/databricks-20260915T045714Z`, cut from `tech-partnerships`.
Target state: `docs/migration/OtterWorks_target_state.md`. Intake: `.migration/00_intake.md`.

## Topology

| Role | Location |
|---|---|
| SOURCE | Oracle AI Database 26ai Free 23.26.3.0.0 on EC2 `ow-tp-oracle` (i-0be201ad6412c5e5e), `52.201.36.9:1521/FREEPDB1`, schema `OW_BILLING` |
| TARGET (analytical) | Unity Catalog `ow_tp`, schemas `bronze` / `silver` / `gold` |
| TARGET (operational) | Lakebase project `ow-tp-billing`, database `ow_tp`, schema `billing` |
| TARGET repo | `Cognition-Partner-Workshops/otterworks` |
| DOCS | same repo: `docs/migration/` and `.migration/` |
| CDC transport | Debezium Server on EKS `otterworks-dev` → Kinesis on-demand → Lakeflow AUTO CDC |

## Track split (OLTP front door)

- **Lakebase (operational):** what the billing application writes transactionally.
- **Delta (analytical):** history, audit, rating results, reporting, everything a report reads.

Full table assignment is in the target state's LAKEBASE profile. An object on both sides is a
write-target collision and a halt.

## Pipelines (strictly sequential; N+1 starts only at N's STOP E)

1. Monthly invoicing (Oracle) — OLTP front door + CDC leg.
2. Finance close (CUSTBILL) — code front door.
3. Product analytics (Python/Scala) — code front door.

Three ordinary build sessions launch in parallel once pipeline 1 reconciles: per-tenant usage
meter, finance gold layer + dashboard, dunning-risk score.

## Process contract

| Item | Value |
|---|---|
| `stop_mode` | soft for A–D; **STOP E always blocks** and is never default-accepted |
| `auto_merge` | false — PASS PRs are held for the wave-close reply |
| Fan-out width | pilot 3, then 5 |
| Circuit breaker | 3 same-class failures halts the wave |
| Recon re-runs | children cap at 3 |
| Cutover principal | held by the engagement owner; Devin never holds or requests it |

## Interaction contract

- Stops and decisions: this web session, one message per event.
- Mirrored copy for visibility: Slack `#ow-migrations` (`C0BQP3P965V`).
- Events that earn a message: a blocking stop, a wave close, a halt. Nothing per child, per
  task, or per green PR.
- Every stop message carries: the link, the decision needed, the recommendation, and the exact
  reply that approves it. The parent never answers on the owner's behalf.
- Question style: one at a time, with a recommended answer and concrete options.

## Notification contract

Slack channel `#ow-migrations` (ID `C0BQP3P965V`), via the Slack integration. Stops may be
read there but are approved here.
