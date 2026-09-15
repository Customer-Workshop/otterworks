# 07 Dependency register

Who else touches OW_BILLING. Four classes. Each row is FOUND, DECIDED (owner and plan
named), or DONE. Filled during the census (playbook 2); decided at STOP B.

| ID | Class | Finding | Evidence | State | Plan |
|---|---|---|---|---|---|
| D1-1 | Other writers | `billing-service` writes the transactional invoice estate | intake; `services/billing-service` | FOUND | census confirms which tables |
| D1-2 | Other writers | the CUSTBILL batch chain writes the conversion feed | intake; `etl/legacy-extra` | FOUND | census confirms which tables |
| D2-1 | Other readers | the stored-proc parity harness reads the estate | intake; `procs/` | FOUND | read-only; unaffected by the migration |
| D3-1 | Scheduled logic | 4 PL/SQL packages plus triggers hold business rules | intake; census pending | FOUND | per object: app code, pipeline, or retire |
| D4-1 | Access | no read-only Oracle user exists on the fixture; the only account is the schema owner `OW_BILLING`, which can write | probed: `06_access_checklist.md` | FOUND | **STOP A decision**: read-only is enforced by discipline (AGENTS.md rule 1) and the write-target allowlist, not by grants. On record. |
