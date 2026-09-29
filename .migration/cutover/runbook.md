# Cutover runbook: legacy-billing Oracle -> MongoDB Atlas

Every production step is executed by the **customer billing team (CX)**. Devin holds no production credential and runs no step marked CX.

## 0. What repoints and what still reads Oracle
- Repoints: every `services/legacy-billing` route (customer account, invoices, plans, entitlement, usage ingest, plan change, month-end, dunning, admin `/billing-report`) via `BILLING_BACKEND=mongo`.
- Still reads Oracle: `etl/legacy-extra/tools/oracle_custbill_extract.py` (DEP-2). After step R3 Oracle is frozen, so this extract reports the watermark state, not live billing. Owner: CX ETL team. Outcome of this cutover: **partial, not full retirement**. Oracle stays up read-only as the rollback target and for DEP-2.
- PL/SQL left on the source: PKG_PLANS, PKG_RATING, PKG_INVOICING, PKG_DUNNING, PKG_OW_UTIL and the 7 triggers stay installed but are no longer called by legacy-billing once it runs on Mongo. JOB_NIGHTLY_DUNNING and JOB_PURGE_AUDIT_LOG stay DISABLED.

## M. Merge before the window (CX, run branch `tp-run/mongodb-20260929T160602Z`)
Merge in this order: #1740 (read-only guard), #1741 (setup + ledger), #1742 (wave 0), #1743 (wave 1), #1744 (U3), #1745 (U2), #1746 (U4 backend + fixture + CI). Deploy legacy-billing from the merged run branch still on `BILLING_BACKEND=oracle`. Nothing changes behaviour until R2.

## F. Freeze and watermark (CX)
F1. Quiesce every Oracle writer: stop `usage-bridge`, do not run month-end, block plan changes (maintenance banner), no admin dunning.
F2. Recount the source read-only: `python .migration/baseline/oracle_recount.py` (with `OW_TP_ORACLE_RO_DSN`). It must equal `baseline/oracle_counts.json`. If it doesn't, stop: re-run the affected unit loaders (idempotent upserts) and their recon at the new watermark before continuing.

## R. Repoint (CX)
R1. Set on the legacy-billing deployment:
  - `BILLING_BACKEND=mongo`
  - `BILLING_MONGO_URI=<CX-held production URI for otterworks-demo, readWrite on ow_tp_mmp_live>`
  - `BILLING_MONGO_DB=ow_tp_mmp_live`
R2. Restart legacy-billing. It refuses to start in mongo mode without `BILLING_MONGO_URI`.
R3. Leave the Oracle writers (F1) stopped. Oracle is now frozen at W.

## V. Verify immediately (CX runs; Devin can run the read-only parts on request)
V1. `/health` is 200 and the admin `/billing-report` shows `source.engine = mongodb`.
V2. Target counts: customers 25,000; invoices 18,750 with 149,963 embedded lines; quarantine_invoice_line 37; billing_invoices 3; subscriptions 69; usage_events 814; tenants 69; plans 3; codes 32.
V3. Page parity against the before captures: Casey Novak DEMO-00000004 account (plan, balance 790386.17, TAX_REGION_OVERRIDE twice); Tenant Two invoice 60000000-0000-0000-0000-000000000001 (149.00 + 12.29 = 161.29, 2 lines); admin billing report totals equal to the cent.
V4. First-cycle recon: `make tp-validate-recon` plus a live harness run on the U2 and U1 collections.

## B. Rollback
- **Trigger (recommended):** any V1-V3 mismatch, or sustained HTTP 503 `UNAVAILABLE` from legacy-billing for more than 5 minutes, within 60 minutes of R2.
- **Procedure (CX):** set `BILLING_BACKEND=oracle`, unset `BILLING_MONGO_URI`, restart legacy-billing. Oracle is at W, so nothing is lost.
- **Point of no return:** the first write accepted on Mongo (usage-bridge restarted, a plan change, month-end or dunning). There is no Mongo-to-Oracle sync. After that point, rolling back loses the writes made after cutover. Keep the F1 writers stopped until V1-V4 pass, then restart them. That restart is the point of no return.

## D. After the rollback window
Oracle stays read-only for as long as CX sets (recommended: 30 days) for rollback and DEP-2. Revoke the migration credentials `OW_TP_MMP_TARGET_URI` (Devin target principal) and `OW_TP_ORACLE_RO_DSN` once post-cutover recon is signed off. Nothing is decommissioned before the rollback window closes.
