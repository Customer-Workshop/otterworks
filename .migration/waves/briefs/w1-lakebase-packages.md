UNITS pkg_ow_util, pkg_plans, pkg_rating, pkg_invoicing (one child: the packages are a call chain
pkg_ow_util -> pkg_plans / pkg_rating -> pkg_invoicing and all four write billing_audit_log through log_msg, so
they cannot be split across children). Convert the Oracle packages
services/legacy-billing/db/oracle/packages/*.sql to Lakebase Postgres (PL/pgSQL) routines in schema `billing`
on branch mig-20260927c-w0, with the names the app backend expects
(services/legacy-billing/app/backends/postgres.py): fn_<name> returns rows, sp_<name> is a procedure.
Load the oracle-plsql skill (dbx-migration-factory:oracle-plsql, OLTP track) before writing code.
1. DDL first, per the four unit mapping specs (.migration/units/<unit>/mapping_spec.json): billing_audit_log;
   subscriptions, subscriptions_hist; rating_periods, rating_results; invoices, invoice_lines, credit_notes;
   plus the sequences/triggers (trg_billing_audit_log_id -> identity default; trg_subscriptions_hist and
   trg_sub_no_uncancel as PL/pgSQL triggers). Load every owned table from Oracle once so the branch is an exact
   copy of Oracle state before any routine runs there.
2. Routines, one file per package under databricks/mig_20260927c/lakebase/1x_pkg_*.sql: f_md5_uuid, f_code_desc,
   f_dt2str, f_str2dt, log_msg, job_purge_audit_log; fn_list_plans, fn_entitlement, sp_change_plan;
   compute_rating, fn_usage_rating, fn_usage_summary, sp_finalize_rating; compute_preview, fn_invoice_preview,
   fn_invoice_lines, sp_issue_invoice. Accepted deviation DEP-003 (STOP B, D-011): log_msg has no autonomous transaction on
   Postgres (it commits with the caller); audit presence and ordering are graded, logged_at is not. Keep Oracle
   rounding (ROUND half away from zero on NUMBER(12,2)), NVL / empty-string semantics, status codes from CODES,
   and the sp_issue_invoice write order (rating_periods, rating_results, invoices, invoice_lines, credit_notes,
   billing_audit_log).
3. Fixture first: develop and prove the golden set on a LOCAL Postgres fixture (make procs-up NS=<ns>, seeded from
   the services/legacy-billing fixtures; Tenant One 00000000-0000-0000-0000-000000000001, plan STARTER,
   260 units on 2026-02-10, period 2026-02-01..2026-02-28). Record golden runs with make procs-record and
   dbx-recon routine-parity; commit them under .migration/recon/<unit_id>/routine_parity/.
   DO NOT execute sp_issue_invoice or sp_change_plan against Lakebase mig-20260927c-w0: the parent runs the live
   invoice on the -exec branch after the wave closes; the w0 branch stays a clean copy of Oracle state.
4. Deploy the routines to mig-20260927c-w0 (psql, literal host, env DSN). Recon live, depth full, on every owned
   table (PASS). Gates: w1-pkg-structural (all routines present, signatures match the backend),
   w1-pkg-routine-parity (dbx-recon routine-parity: every routine proven, exit 0), w1-pkg-state-parity
   (row_parity, depth full, PASS on the 8 owned tables), w1-pkg-invoice-fixture (fixture issue_invoice for
   Tenant One yields subtotal / tax / total identical to the Oracle fixture run; both rows recorded side by side
   under .migration/recon/pkg_invoicing/).
Write targets: ow_tp.billing.billing_audit_log, subscriptions, subscriptions_hist, rating_periods,
rating_results, invoices, invoice_lines, credit_notes and the routines in deploy_objects (Lakebase branch
mig-20260927c-w0 only). Give each unit its own section in the PR body.
