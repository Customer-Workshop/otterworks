# _slice callgraph — transitive call/write closure (run 20260927b)

Static analysis of `services/legacy-billing/db/oracle/packages/0[1-5]_pkg_*.sql`,
`schema/01_tables.sql`, `schema/02_horror.sql`, `schema/04_jobs.sql`,
`services/legacy-billing/app/backends/oracle.py`, `etl/legacy-extra/tools/oracle_custbill_extract.py`.

## Roots

- `pkg_invoicing.sp_issue_invoice` (issue_invoice slice path)
- `pkg_plans.sp_change_plan` + `pkg_plans.fn_entitlement`/`fn_list_plans` (signup/subscription path; `backends/oracle.py` `ensure_tenant` does direct INSERTs into `tenants`/`subscriptions`, `oracle.py:150-177`)
- CUSTBILL extract (`tools/oracle_custbill_extract.py` `EXTRACT_SQL` — pure SELECT, no calls)

## Transitive closure

```
sp_issue_invoice
  -> pkg_ow_util.f_md5_uuid                     (no I/O)
  -> pkg_rating.sp_finalize_rating
       -> pkg_ow_util.f_md5_uuid
       -> pkg_rating.compute_rating
            reads subscriptions, plans, usage_events, rating_results, rating_periods
            -> pkg_ow_util.log_msg -> writes billing_audit_log
       writes rating_periods, rating_results
  -> fn_invoice_preview -> compute_preview
       reads subscriptions, plans, credit_notes, tenants
       -> pkg_rating.compute_rating  (as above)
  writes invoices, invoice_lines, credit_notes
  -> pkg_ow_util.log_msg -> writes billing_audit_log

sp_change_plan
  reads subscriptions; writes subscriptions
  fires trg_subscriptions_hist -> writes subscriptions_hist
  fires trg_sub_no_uncancel     -> forces status_cd=30 (no I/O)
  -> pkg_ow_util.f_md5_uuid, pkg_ow_util.log_msg -> billing_audit_log

fn_entitlement / fn_list_plans / fn_usage_rating / fn_usage_summary /
fn_invoice_preview / fn_invoice_lines  (read path)
  reads plans, tenants, subscriptions, usage_events, invoice_lines
  -> log_msg (fn_list_plans only), compute_rating (fn_usage_rating)

CUSTBILL extract
  reads invoice_header, customer_master, tenants   (SELECT only; zero calls)
```

## Tables touched by the closure

- reads: `codes` (f_code_desc, not in the closure roots above but in pkg_ow_util), `plans`, `tenants`, `subscriptions`, `usage_events`, `rating_periods`, `rating_results`, `invoices`(? — no: `invoices` is written not read), `invoice_lines`, `credit_notes`, `invoice_header`, `customer_master`
- writes: `subscriptions`, `subscriptions_hist` (trigger), `rating_periods`, `rating_results`, `invoices`, `invoice_lines`, `credit_notes`, `billing_audit_log`

## The pkg_dunning question — FACT, not decided

**Nothing in the slice closure calls into `PKG_DUNNING`, and nothing in it reads or
writes a table that only `pkg_dunning` owns.** Evidence:

- Every `calls` edge in `.migration/units/{pkg_ow_util,pkg_plans,pkg_rating,pkg_invoicing}/dependencies.json` terminates inside those four packages or their triggers; `pkg_dunning` appears nowhere as a callee. (`grep pkg_dunning` on those four package files returns zero hits outside `05_pkg_dunning.sql`.)
- `dunning_attempts` is written only by `pkg_dunning.sp_schedule_dunning` (`05_pkg_dunning.sql:478`) and `notifications` only by `pkg_dunning.sp_suspend_overdue` (`05_pkg_dunning.sql:511`); neither table is read or written anywhere in the closure.
- The only inbound callers of `pkg_dunning` are `JOB_NIGHTLY_DUNNING` (`04_jobs.sql:13`, DISABLED) and the app's `backends/oracle.py` `overdue`/`schedule_dunning`/`suspend_overdue` (`oracle.py:172-181`) — none of which is signup, subscription, issue_invoice, CUSTBILL, or the finance close.
- Shared tables `tenants`/`subscriptions` are written by both the slice (`sp_change_plan`, app `ensure_tenant`) and `sp_suspend_overdue`, so the *tables* are shared — but the *call edge* does not exist.

This matches DEP-010 (PROPOSED: `pkg_dunning` not pulled in). Reported as fact for STOP B; the scope decision is the approver's.
