# 04 — Dependency register

Classes: D1 intra-pipeline lineage · D2 shared object · D3 upstream feed · D4 downstream consumer · D5 scheduler · D6 shared-write table · D7 external hand-off · D8 security/governance · D9 ML consumer · D10 environment/access.
Status flow: OPEN → DECIDED (federate / re-point / dual-write / defer-with-condition / accept) → IMPLEMENTED → CLOSED. Lead-time requests are fired at registration, never at cutover.

| ID | Class | Item | Contract | Decision | Routing point / cutover condition | Request fired | Status | Registered by |
|---|---|---|---|---|---|---|---|---|
| D3-1 | D3 | `DW_ETL_PKG` reads `COMMISSION_PAY.AGENTS`, `PRODUCTS`, `POLICIES`, `COMMISSION_LEDGER` (non-migrating schema) | Snapshot the four tables read-only to bronze (`ow_tp.bronze.cp_<table>_cdw`) with manifest; batch granularity = per period_month, on demand; empty input = zero-row load, not an error; malformed rows = quarantine | → plan (STOP C) | Converted loader reads bronze; post-cutover feed mechanism decided at STOP C (snapshot job vs customer export) | none needed (read-only extract) | IMPLEMENTED (wave 2, #1431: T0 feed refresh via cdw_baseline.py load-feed; post-cutover extract = customer-run, STOP E) | intake |
| D4-1 | D4 | Downstream consumers of `COMMISSION_DW` / the MV | None detectable: no object grants; `V$SQL`/AWR not granted (not requestable — would modify legacy) | evidence gap declared; code-search sweep in inventory | if none found: cutover = publish gold + document | — | IMPLEMENTED (gold ow_tp.gold.mv_agent_commission_summary_cdw landed #1431; consumer evidence gap stands → STOP E) | intake |
| D10-1 | D10 | Lakehouse Federation to source | Source is loopback-only inside Docker Compose; no network path from the workspace | accept: snapshot coexistence, recon **DEGRADED** | in-perimeter recon by customer is a STOP E entry criterion | — | ACCEPTED (confirm STOP A) | intake |
| D10-2 | D10 | `ow_tp` catalog absent (preflight 7/10) | Wave 0 creates `ow_tp` + `bronze/silver/gold/ops`; preflight re-run to 10/10 before any child launch | create (permitted: `ow_tp` is our prefix) | — | wave 0 | OPEN → wave 0 | intake |
| D10-3 | D10 | Query-history views not granted to `commission_dw` | Would require modifying legacy grants | accept (not requestable) | — | — | ACCEPTED | intake |
| D8-1 | D8 | Person data: `DIM_AGENT.full_name` | No legacy masking/RLS policy exists | propose: no UC mask; recorded so cutover grants stay least-privilege (SELECT on gold only) | STOP E grants | — | PROPOSED (STOP A) | setup |
| D5-1 | D5 | Scheduler | No `DBMS_SCHEDULER` job or cron invokes the loader; runs on demand | target job schedule PAUSED, trigger by hand | — | — | IMPLEMENTED (job 939320833644147 PAUSED, monthly cron 0 0 6 1 * ? UTC, manual trigger) | setup |

## Plan-time decisions — DECIDED at STOP C (2026-09-01); see `COMMISSION_DW_plan.md` §1
| ID | Proposed decision | Routing point | Cutover condition | Fired request |
|---|---|---|---|---|
| D3-1 | Snapshot ingestion contract: CSV + `manifest.json` in `/Volumes/ow_tp/bronze/landing/cdw/feed/` → `ow_tp.bronze.<table>_cdw`; customer-run extract post-cutover | volume path | valid customer-produced manifest | none |
| D4-1 | Accept evidence gap; gold table is the report surface; customer re-points at STOP E | `ow_tp.gold.mv_agent_commission_summary_cdw` | consumers named or confirmed none | none |
| D5-1 | Workflow `ow_tp_cdw_load_commission_facts`, PAUSED, manual trigger | the job | STOP E | none |
| D8-1 | No UC masks/filters; SELECT on gold `_cdw` to engagement principals only | UC grants | before consumer re-point | none |
| D10-2 | Wave 0 creates `ow_tp` + schemas + volume; preflight 10/10 is wave-0 exit gate | — | — | none |
