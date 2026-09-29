# 07 Dependency register (started at setup, filled at phase 2)

| ID | Class | Dependency | State | Owner / plan |
|---|---|---|---|---|
| DEP-1 | D1 Other writers | Only legacy-billing writes, through PKG_PLANS (plan change), PKG_RATING (usage via usage-bridge HTTP), PKG_INVOICING, PKG_DUNNING and `ensure_tenant`. DBA census: 0 other sessions, 0 grants to other principals | DONE (U4, #1746) | Mongo backend (U4) reimplements each path; source frozen until cutover (customer billing owner, STOP C) |
| DEP-2 | D2 Other readers | admin `/billing-report` via legacy-billing `reports.py` (ported in U4); `etl/legacy-extra/tools/oracle_custbill_extract.py` reads Oracle directly; `procs/harness/oracle_record.py`, `scripts/tp_pain/*`, `scripts/tp_dbx/demo_reset.py` are demo/test tooling | DONE (report, U4) / DEFERRED (CUSTBILL extract, owner: customer billing/ETL team) | reports: U4. CUSTBILL extract: stays on Oracle, customer-owned (D-011). Tooling: out of scope |
| DEP-3 | D3 Scheduled logic | JOB_NIGHTLY_DUNNING, JOB_PURGE_AUDIT_LOG: DISABLED, 0 runs. 7 triggers ENABLED (mapped in inventory/model.md). PKG_OW_UTIL autonomous transaction | DONE (triggers + autonomous log in U4; jobs dispositioned, DISABLED) | jobs not ported (dunning stays on-demand via admin endpoint); triggers and autonomous log ported in U4 |
| DEP-4 | D4 Access | `OW_TP_MMP_TARGET_URI` principal over-scoped (privilege_excess) | RESOLVED 2026-09-29 | rescoped to readWrite@ow_tp_mmp_live (D-007/D-010) |
| DEP-5 | D4 Access | Org statement guard cannot read the plugin probe's dict-built SQL | RESOLVED | literal-statement port in `.migration/tools/` (D-008) |
| DEP-6 | D4 Cutover | Repoint = restart legacy-billing with `BILLING_BACKEND=mongo` and `OW_TP_MMP_TARGET_URI`; Oracle stays untouched as rollback | CUSTOMER-HELD (runbook `cutover/runbook.md`) | customer billing team executes (STOP C) |
