# 06_access_checklist

## Environment fix (customer instruction, run once, 2026-09-26)
```
~/.venvs/recon/bin/python -m pip install -U pip setuptools
~/.venvs/recon/bin/python -m pip install -e "<plugin cache>/skills/mongo-recon-harness/harness[all,test]"
~/.venvs/recon/bin/recon selftest
```
Outcome: install succeeded; `recon selftest` -> `PASS: 9 canonicalization rules exercised`.

## Customer pre-engagement steps (not migration work)
| Step | Outcome |
|---|---|
| `make oracle-billing-up` | container `otterworks-oracle-billing-oracle-billing-1` healthy, `0.0.0.0:52521->1521/tcp` |
| `make oracle-billing-seed NS=mmprt SCALE=demo` | CUSTOMER_MASTER 25000, INVOICE_HEADER 18750, INVOICE_LINE 150000 (37 orphans), ENTITY_ATTR_VALUE 8333, 60 core tenants |
| DBA: `CREATE USER ow_billing_ro` + `GRANT CREATE SESSION` + `GRANT SELECT` per `ALL_TABLES WHERE owner='OW_BILLING'` | done inside the container as SYSTEM (`sqlplus ... @localhost:1521/FREEPDB1`, the in-container port per `.agents/skills/oracle-billing-estate/SKILL.md`); 20 table grants |

## Probe results (policy `online`, `connectivity_probe.py`, 2026-09-26 16:56-16:59 UTC)
| Side | Secret (name) | Result | Evidence |
|---|---|---|---|
| Source, attempt 1 | `ORACLE_BILLING_DSN` (`ow_billing`, app owner) | **BLOCKED** `privilege_excess`: CREATE JOB, CREATE TYPE, CREATE TRIGGER, CREATE PROCEDURE, CREATE SEQUENCE, CREATE VIEW, CREATE TABLE | `08_connectivity.attempt1-ORACLE_BILLING_DSN.json`. Not risk-accepted; the credential is not used for any migration read. |
| Source, attempt 2 | `ORACLE_BILLING_RO_DSN` (`ow_billing_ro`) | **WORKS** `live` / `probe_ok` (CREATE SESSION + SELECT only) | `08_connectivity.json` |
| Target | `MONGODB_MMP_RT_TARGET_URI` -> `mmp_rt_billing` | **BLOCKED** malformed secret: the value is a 16-character alphanumeric token, not a connection string (no scheme, no `@`, no host, no database). pymongo treated it as a bare hostname and failed DNS; the driver error echoed the value, so `detail` in both connectivity files is redacted. | `08_connectivity.json`; D4-2 |
| Offline guard | `offline_guard.py --repo . --source live --target migration_cluster --target-env MONGODB_MMP_RT_TARGET_URI` | OK (only checks that the variable is set) | note: the probe's printed command omits `--target-env`, so as printed it would have inspected `MONGODB_ATLAS_URI`, which this engagement forbids; run with `--target-env`. |

Diagnostics (read-only Atlas Admin API, project `otterworks-demos`): database user `mmp_rt_target` exists with roles `readWrite@mmp_rt_billing`, `readWrite@mmp_rt_billing_n`; cluster `otterworks-demo` exists. Only the secret value is wrong.

## D4 requests (drafted; who approves, what, how)
| Id | Item | Approver | Request |
|---|---|---|---|
| D4-1 | `ORACLE_BILLING_DSN` over-scoped | customer DBA | none needed: `ORACLE_BILLING_RO_DSN` replaces it for every migration read. Recorded as evidence only. |
| D4-2 | `MONGODB_MMP_RT_TARGET_URI` is not a URI | customer / org secret owner | Re-store the org secret `MONGODB_MMP_RT_TARGET_URI` as a full connection string for user `mmp_rt_target` on cluster `otterworks-demo`, e.g. `mongodb+srv://mmp_rt_target:<password>@<otterworks-demo SRV host>/mmp_rt_billing?retryWrites=true&w=majority`. Devin will not assemble a URI from the token plus API-discovered host (that would be Devin constructing a credential). Then re-run `!mongo_migrate`; it re-probes and reopens STOP A. |

## Access model (for the security reviewer)
| Tier | Purpose | Secret name (Cloud: Devin Secrets; Local: env var of the same name) | Scope |
|---|---|---|---|
| 1 Assessment read-only | census, one live read per unit, recon source side | `ORACLE_BILLING_RO_DSN` | Oracle `ow_billing_ro`: CREATE SESSION + SELECT on OW_BILLING tables; concurrency 1; this VM only |
| 2 Migration write | loaders + recon target side | `MONGODB_MMP_RT_TARGET_URI` | Atlas `mmp_rt_target`: readWrite on `mmp_rt_billing` only (allowlist `allowed_targets.json`) |
| 3 Cutover | production repoint | held by the customer DBA (not present); Devin never holds or requests it | n/a |

Not used: `ORACLE_BILLING_DSN` (over-scoped, evidence only), `MONGODB_ATLAS_URI` (readWriteAnyDatabase; forbidden for this engagement).
Audit: Devin session https://partner-workshops.devinenterprise.com/sessions/96b8955d22a2477ba2cffcbc67cab7a9; Oracle side via `ow_billing_ro` sessions in `V$SESSION`/audit trail; Atlas side via project Access Tracking filtered on user `mmp_rt_target`.

## Re-probe 2026-09-26 17:02 UTC (after the customer re-stored the target secret)
| Side | Secret (name) | Result |
|---|---|---|
| Source | `ORACLE_BILLING_RO_DSN` | WORKS `live` / `probe_ok` |
| Target | `MONGODB_MMP_RT_TARGET_URI` (`mmp_rt_target`) | **BLOCKED** `privilege_excess`: `readWrite@mmp_rt_billing_n` beyond the allowlisted `mmp_rt_billing` (D4-3). Value now a valid `mongodb+srv://` string (D4-2 DONE). |
| Offline guard | `--target-env MONGODB_MMP_RT_TARGET_URI` | OK |

## Re-probe 2026-09-26 17:0x UTC (after the customer removed the extra role)
source `ORACLE_BILLING_RO_DSN` live/probe_ok; target `MONGODB_MMP_RT_TARGET_URI` migration_cluster/probe_ok; offline guard OK. STOP A passed.
