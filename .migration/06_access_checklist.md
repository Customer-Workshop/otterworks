# 06 Access checklist and access model

## Status

| Item | Secret / path | State | Evidence |
|---|---|---|---|
| Oracle read (assessment tier) | `OW_TP_ORACLE_RO_DSN` | WORKS | privileges: CREATE SESSION, SELECT ANY TABLE, SELECT ANY DICTIONARY (read-only; broader than OW_BILLING but no write grant) |
| Oracle app read for captures | `OW_TP_ORACLE_APP_PASSWORD` + `BILLING_READONLY=1` | WORKS | before capture done, recount matched |
| Atlas migration write (migration tier) | `OW_TP_MMP_TARGET_URI` -> `ow_tp_mmp_live` | WORKS (rescoped 2026-09-29) | roles: readWrite@ow_tp_mmp_live only; insert/delete probe in `_connectivity_probe` ok. Earlier: privilege_excess (dbAdmin@ow_tp_mmp_live, readWrite+dbAdmin@ow_tp_mmp_live_quarantine) |
| Cutover (cutover tier) | customer-held | NOT APPLICABLE to Devin | customer team repoints production |
| Network Devin -> Oracle | 52.201.36.9:1521 | WORKS | probe connected |
| Network Devin -> Atlas | otterworks-demo | WORKS | connectionStatus returned |

## Request for the formerly BLOCKED item (D4), resolved 2026-09-29

Approver: the Atlas project owner for `otterworks-demo`.
Change: the database user inside `OW_TP_MMP_TARGET_URI` keeps exactly one role,
`readWrite@ow_tp_mmp_live`. Remove dbAdmin on `ow_tp_mmp_live` and both roles on
`ow_tp_mmp_live_quarantine` (quarantine lives as collections inside `ow_tp_mmp_live`).
Suggested command (run by the owner; `--role` replaces all existing roles):

    atlas dbusers update <user-in-OW_TP_MMP_TARGET_URI> --role readWrite@ow_tp_mmp_live --projectId <otterworks-demo project id>

Validators and indexes are created with the collection, which `readWrite` allows, so `dbAdmin`
is not needed. After the change Devin re-runs the probe and records the result here.

## Access model (for the security reviewer)

| Tier | Purpose | Secret name | Scope |
|---|---|---|---|
| Assessment, read-only | census, fixtures metadata, the single live recon read, recounts | `OW_TP_ORACLE_RO_DSN` | SELECT only, no write grant |
| Capture, read-only by config | before/after app screenshots against Oracle | `OW_TP_ORACLE_APP_PASSWORD` | app user, used only with `BILLING_READONLY=1` and read-only pages |
| Migration write | loaders and recon into the migration database | `OW_TP_MMP_TARGET_URI` | `readWrite@ow_tp_mmp_live` only (after the fix) |
| Cutover | production repoint | customer-held, never requested by Devin | customer |

Audit: Oracle sessions from this run connect from the Devin VM as the RO user; Atlas activity
appears under the database user of `OW_TP_MMP_TARGET_URI` in the otterworks-demo project
activity feed and database access history. Session: https://partner-workshops.devinenterprise.com/sessions/b17b175e687e4b7093c1d2f6883271da
