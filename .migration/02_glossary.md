# 02 — Glossary

| Term | Meaning |
|---|---|
| Commission Pay | The insurance agent-commission system: OLTP schema `COMMISSION_PAY` (agents, products, policies, commission ledger, `COMMISSION_PKG` rules) plus the reporting warehouse `COMMISSION_DW`. |
| `COMMISSION_DW` | Star-schema warehouse: `DIM_AGENT`, `DIM_PRODUCT`, `DIM_PERIOD`, `FACT_COMMISSION`, summary MV. In scope. |
| `DW_ETL_PKG.LOAD_COMMISSION_FACTS` | PL/SQL loader; MERGE-based, per period, idempotent; reads `COMMISSION_PAY`, writes the dimensions and the fact. |
| `MV_AGENT_COMMISSION_SUMMARY` | Materialized view (COMPLETE refresh on DEMAND) of commission by agent × period_month × line_of_business. |
| `UX_FACT_ROW` | Unique index on `FACT_COMMISSION` natural columns; the recon key and MERGE key. |
| `*_key` | Identity surrogate keys (`agent_key`, `product_key`, `period_key`, `fact_id`); preserved as explicit BIGINT values on the target. |
| `loaded_at` | Server-side `SYSTIMESTAMP` on the fact; excluded from every comparison. |
| Period | A calendar month (`period_month`, first day of month) — the ETL's batch granularity. |
| Line of business | Product classification carried on `DIM_PRODUCT`; a grouping column of the MV. |
| ns / namespace | Run isolation suffix on every Databricks object (`_cdw`) and volume path. |
| Snapshot / baseline | Deterministic read-only extract of legacy tables (CSV + manifest) used as recon truth (DEGRADED mode). |
| Recon mode DEGRADED | Comparison is against a snapshot, not live legacy; every verdict says so. |
| D3 / D4 / D10 | Dependency classes: upstream feed / downstream consumer / environment-access. |
| STOP A…E | Human checkpoints (A target+tolerances+access, B pipeline, C plan, D wave close, E cutover). |
| Wave | Lineage-ordered batch of units migrated in parallel; wave 0 is shared scaffolding, wave 1 the pilot. |
