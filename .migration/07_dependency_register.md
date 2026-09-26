# 07_dependency_register

Four classes only. States: FOUND, DECIDED (owner and plan named), DONE.

| Id | Class | Object / finding | Owner | Plan | State |
|---|---|---|---|---|---|
| D1 Other writers | | (filled in playbook 2) | | | |
| D2 Other readers | | (filled in playbook 2) | | | |
| D3 Scheduled logic | | (filled in playbook 2) | | | |
| D4-1 | D4 Access | `ORACLE_BILLING_DSN` (app owner) over-scoped: CREATE JOB/TYPE/TRIGGER/PROCEDURE/SEQUENCE/VIEW/TABLE | customer DBA | superseded by `ORACLE_BILLING_RO_DSN` (probe_ok); credential not used | DECIDED |
| D4-2 | D4 Access | `MONGODB_MMP_RT_TARGET_URI` value is a 16-char token, not a connection string; target probe BLOCKED | customer / org secret owner | re-store the secret as a full `mongodb+srv://mmp_rt_target:...@<otterworks-demo>/mmp_rt_billing` URI, then re-run `!mongo_migrate` | DONE (2026-09-26 17:02, secret re-stored; target probe now reaches the cluster) |
| D4-3 | D4 Access | `MONGODB_MMP_RT_TARGET_URI` principal `mmp_rt_target` over-scoped: `readWrite@mmp_rt_billing_n` in addition to `readWrite@mmp_rt_billing`; target probe BLOCKED `privilege_excess` | customer / Atlas project owner | remove the `readWrite@mmp_rt_billing_n` role from `mmp_rt_target` (Atlas UI: Database Access -> mmp_rt_target -> Edit; or Admin API PATCH `/groups/<project>/databaseUsers/admin/mmp_rt_target` with roles = [readWrite@mmp_rt_billing]); then re-run `!mongo_migrate`. Alternatively a customer-signed risk-accept row naming the credential, the excess role, approver and expiry — Devin does not recommend this | DONE (2026-09-26, role removed by the customer; target probe_ok) |
