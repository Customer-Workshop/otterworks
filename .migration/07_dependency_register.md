# 07_dependency_register

Four classes only. States: FOUND, DECIDED (owner and plan named), DONE.

| Id | Class | Object / finding | Owner | Plan | State |
|---|---|---|---|---|---|
| D1 Other writers | | (filled in playbook 2) | | | |
| D2 Other readers | | (filled in playbook 2) | | | |
| D3 Scheduled logic | | (filled in playbook 2) | | | |
| D4-1 | D4 Access | `ORACLE_BILLING_DSN` (app owner) over-scoped: CREATE JOB/TYPE/TRIGGER/PROCEDURE/SEQUENCE/VIEW/TABLE | customer DBA | superseded by `ORACLE_BILLING_RO_DSN` (probe_ok); credential not used | DECIDED |
| D4-2 | D4 Access | `MONGODB_MMP_RT_TARGET_URI` value is a 16-char token, not a connection string; target probe BLOCKED | customer / org secret owner | re-store the secret as a full `mongodb+srv://mmp_rt_target:...@<otterworks-demo>/mmp_rt_billing` URI, then re-run `!mongo_migrate` | FOUND |
