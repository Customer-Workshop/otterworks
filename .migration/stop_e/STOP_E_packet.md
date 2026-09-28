# STOP E packet: OtterWorks billing -> Databricks, run 20260927c

Decision requested: repoint production consumers (legacy-billing -> Lakebase `production`, CUSTBILL consumers -> Lakeflow) or decline.
Recommended and expected answer: **decline the repoint**. Production Oracle `OW_BILLING` and Lakebase branch `production` have not moved and will not move.

## Side-by-side evidence (legacy | Databricks | dbx-recon)
See `what_moved.md` for the one-screen table. Raw artifacts in `evidence/`:
- Invoice row (Tenant One, Feb-2026): `evidence/pkg_invoicing_invoice_fixture.json` (Oracle vs Lakebase exec, verdict PASS), recon `evidence/pkg_invoicing_result.json`.
- Live issue_invoice (Tenant One, Mar-2026), recorded: Lakebase exec invoice `8faeec95-94c1-b099-c60d-3857d0481bf1` total 53.04, 5 lines, status 20; identical id/amounts/lines on the local Oracle fixture (recording 3).
- CUSTBILL file sha256: `evidence/custbill_lakeflow_custbill_sha256.json` (legacy = databricks = `c3e2cf43e099f9e17cc59a2b202cd876c103b8f21a8693eba45fb5fd7eb946db`, 18,750 records), recon `evidence/custbill_lakeflow_result.json`, bronze counts `evidence/custbill_lakeflow_live_counts.json`, quarantine `evidence/custbill_lakeflow_quarantine_fixture.json`.
- Finance close total: `evidence/finance_close_gold_close_total.json` (gold = SUM(detail) = legacy = Tier-2 = 187618458.58), recon `evidence/finance_close_gold_result.json`.
- Dashboard: https://dbc-8bc9474f-40ae.cloud.databricks.com/dashboardsv3/01f1badd479f1e18b2b20b3879389b06/published?w=7474651138173478

## Recordings (mp4, not committed; sha256 in `recordings.sha256`)
The OtterWorks application itself (web-app :3000 and admin-dashboard :4200 via the api-gateway, `make tp-up` estate), with the api-gateway's `/api/v1/billing` pointed at the same legacy-billing service on Oracle (local fixture, :8096) and then on Lakebase `mig-20260927c-exec` schema `billing` (:8097). Needs PR #1733 (facade follows `BILLING_BACKEND`; before it the Lakebase side answered 501). Web login is a local auth-service user mapped to Tenant One's UUID; no Oracle tenant was created.
1. `01-legacy-flow.mp4`: web-app Plans / Overview / Account / Invoices (Tenant One STARTER 49.00, Feb invoice `109bb68d-...` 5 lines = 53.04) and the admin Billing Report page (RPT-114 month-end 18,750 invoices / 187,618,458.58, CUSTBILL finance section), all on Oracle.
2. `02-databricks-flow.mp4`: same pages, same tenant, gateway on Lakebase exec: same invoice id, lines and 53.04. Admin Billing Report shows its load error on this side: month-end/reconciliation read the CUSTBILL batch tables, which moved to Delta gold + the dashboard, not Lakebase, so they answer 501 (not silently Oracle); the finance CSV endpoint still answers 200 but the page hides that panel when the main report fails. Ends at the dashboard login wall (no browser session for the SP).
3. `03-live-issue-invoice.mp4`: live issue_invoice for May-2026 on both sides (the web-app has no issue button, so the POST is the service's own form, then the resulting invoice is shown in the web-app on each side): both `issued`, same invoice id `afb70fae-4123-26fd-48b1-d41db7e9d94f`, 5 lines = 53.04 on both.
Known gaps, unchanged app code: the web-app Overview page carries a static "Oracle" source label on both sides; the dashboard could not be shown authenticated. Earlier service-page and terminal recordings kept on the box only.

## PRs (run branch `tp-run/databricks-20260927T194945Z`; human merges)
#1729 wave 0 scaffold, #1730 wave 1 packages, #1731 wave 1 CUSTBILL Lakeflow, #1732 wave 2 finance close gold + dashboard, #1733 legacy-billing facade through the backend switch (consumer-side, run branch only; enables the application recordings).

## Decisions
D-009 STOP A, D-011 STOP B, D-013/14/15 STOP C, D-016 w0 override, D-021 w0 accept, D-022 w1 fixes, D-023 w1 override, D-024 w2 override. Independent verifier never ran (mechanical gate); parity rests on live dbx-recon PASS per unit.

## Production unchanged
Lakebase `production` (uid br-tiny-scene-d11ud3z5): default, logical_size_bytes 31383552, last update_time 2026-09-27T20:07:14Z (before wave 0 launch; w0/exec branches were created from it). No writes by this run. Oracle OW_BILLING accessed read-only only. Shared ow_tp.bronze/silver/gold untouched.
