# 06 — Decision log

All decisions below were settled at intake on **2026-08-28** and must not be re-asked at
STOP A.

| ID | Decision | Owner | Date | Evidence |
|---|---|---|---|---|
| SCOPE-1 | `OW_BILLING` only; `COMMISSION_DW` is out of scope for this run. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:149-154` |
| DATA-1 | Lakehouse Federation over JDBC to Oracle is approved; coexistence is federation-first and recon mode is `LIVE`. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:138-145,153-154` |
| TOL-1 | Money comparisons are exact to the cent; money remains `DECIMAL(14,2)`. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:155-156` |
| TOL-2 | Unparseable `VARCHAR2(9)` dates quarantine the row, continue loading, and count in recon. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:155-156` |
| PILOT-1 | Pilot is exactly `PKG_RATING` plus `PKG_INVOICING`. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:157` |
| D4-1 | Consumer population is declared `UNMAPPED`; carry it as an explicit coverage gap. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:157-159,169-176` |
| D10-1 | Use targeted grants, not `SELECT_CATALOG_ROLE`; grants are applied and verified. | Customer / DBA | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:159,178-194` |
| D4-2 | No audit observation window; customer accepted the unmapped-consumer risk. | Customer | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:160,196-224` |
| NOTIFY-1 | Route only blocking STOP A/B/C/E readiness, STOP D wave close with exception count, and fan-out halts to `#ow-migrations` (`C0BQP3P965V`). | Migration lead | 2026-08-28 | `docs/tech-partnerships/dbx-frontdoor-intake-billing-warehouse.md:233-236`; `.migration/00_context.md` |
| STOPA-PII | Mask PII on read: real `CUSTOMER_MASTER` values land in bronze/silver, and Unity Catalog column masks restrict cleartext to the migration principal only. | Customer | 2026-08-28 | Customer STOP A decision; `docs/tech-partnerships/OW_BILLING_target_state.md:99-100` |
| STOPA-HIST | Retire `_HIST` trigger capture going forward, but migrate `CUSTOMER_MASTER_HIST` and `SUBSCRIPTIONS_HIST` as first-class tables. `HIST_DT` is a quarantinable `DD-MON-YY HH24:MI:SS` string, `HIST_OP` carries `UPD`/`DEL`, deleted state may exist only there, and Delta history cannot provide pre-cutover history. | Customer | 2026-08-28 | Customer STOP A decision; `docs/tech-partnerships/OW_BILLING_target_state.md:38,51` |
| STOPA-TRIGGERS | Make the five remaining trigger rules explicit and tested in pipeline logic: `trg_sub_no_uncancel`, `trg_usage_events_check`, `trg_customer_master_seq`, `trg_entity_attr_value_seq`, and `trg_billing_audit_log_id`. | Customer | 2026-08-28 | Customer STOP A decision; `docs/tech-partnerships/OW_BILLING_target_state.md:40,54` |
| STOPA-QUARANTINE | Confirm the quarantine halt threshold at 5% of source rows; the unit halts and escalates above that rate. | Customer | 2026-08-28 | Customer STOP A decision; `.migration/03_recon_tolerances.md:48-50` |
| STOPA-CONTENTION | Never run DDL against shared tables; never accept a recon green only in a contended window. State `ns` and make each unit recon re-runnable. The PAT's `files` scope for `/Volumes/ow_tp/bronze/landing` is verified present. | Customer | 2026-08-28 | Customer STOP A decision; `.migration/01_conventions.md:17-19` |
