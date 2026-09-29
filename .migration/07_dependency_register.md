# 07 Dependency register (started at setup, filled at phase 2)

| ID | Class | Dependency | State | Owner / plan |
|---|---|---|---|---|
| DEP-1 | D1 Other writers | legacy-billing writes: plan changes (PKG_PLANS), usage events (usage-bridge, PKG_RATING), month-end / invoicing (PKG_INVOICING), dunning (PKG_DUNNING), tenant auto-provisioning (`ensure_tenant`) | FOUND | inventoried at STOP B; frozen during the run (no writes) |
| DEP-2 | D2 Other readers | admin `/billing-report` (month-end + reconciliation endpoints), finance reports, `etl/legacy-extra` tools | FOUND | inventoried at STOP B |
| DEP-3 | D3 Scheduled logic | DBMS_SCHEDULER jobs (`schema/04_jobs.sql`); triggers: trg_customer_master_seq/_hist, trg_entity_attr_value_seq, trg_billing_audit_log_id, trg_subscriptions_hist, trg_sub_no_uncancel, trg_usage_events_check | FOUND (repo DDL) | confirm live via ALL_SCHEDULER_JOBS / ALL_TRIGGERS at phase 2 |
| DEP-4 | D4 Access | `OW_TP_MMP_TARGET_URI` principal over-scoped (privilege_excess) | RESOLVED 2026-09-29 | Atlas project owner rescopes to readWrite@ow_tp_mmp_live (06_access_checklist.md) |
| DEP-5 | D4 Access | Org statement guard cannot read the plugin probe's dict-built SQL | FOUND | literal-statement port in `.migration/tools/` (D-008) |
