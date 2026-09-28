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
1. `01-legacy-flow.mp4`: fixture signup/subscription state, Feb issue_invoice on Oracle, ksh/perl CUSTBILL chain -> sha256 + close total.
2. `02-databricks-flow.mp4`: gold close total, CUSTBILL manifest sha256, Lakeflow update COMPLETED (0e649210-...), job run 662817900379275 SUCCESS, expectations 18,750 pass / 0 fail, quarantine sample. Dashboard shown via committed evidence + live metadata: the browser had no workspace session for the SP and the guard blocks SQL statement POSTs from the session (findings, not bypassed).
3. `03-live-issue-invoice.mp4`: live CALL billing.sp_issue_invoice on `mig-20260927c-exec` for Mar-2026 next to the same call on the Oracle fixture.
Caveats: signup/subscription in recording 1 are pre-seeded fixture rows, not a fresh signup; pipeline shows IDLE (non-continuous), PAUSED is the render job schedule.

## PRs (run branch `tp-run/databricks-20260927T194945Z`; human merges)
#1729 wave 0 scaffold, #1730 wave 1 packages, #1731 wave 1 CUSTBILL Lakeflow, #1732 wave 2 finance close gold + dashboard.

## Decisions
D-009 STOP A, D-011 STOP B, D-013/14/15 STOP C, D-016 w0 override, D-021 w0 accept, D-022 w1 fixes, D-023 w1 override, D-024 w2 override. Independent verifier never ran (mechanical gate); parity rests on live dbx-recon PASS per unit.

## Production unchanged
Lakebase `production` (uid br-tiny-scene-d11ud3z5): default, logical_size_bytes 31383552, last update_time 2026-09-27T20:07:14Z (before wave 0 launch; w0/exec branches were created from it). No writes by this run. Oracle OW_BILLING accessed read-only only. Shared ow_tp.bronze/silver/gold untouched.
