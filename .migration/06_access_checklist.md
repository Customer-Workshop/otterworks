# 06 Access checklist

Probed 2026-09-15. Each row is VERIFIED (a real call succeeded), DENIED, or UNKNOWN.

| # | Access | State | Evidence |
|---|---|---|---|
| A1 | Oracle source read, schema `OW_BILLING` | VERIFIED | `sqlplus ow_billing@localhost:1521/FREEPDB1` in container `otterworks-oracle-billing-oracle-billing-1`; census counts returned |
| A2 | Oracle **read-only** account | **DENIED — no such account exists** | `all_users where oracle_maintained='N'` → `OW_BILLING, PDBADMIN` only. `session_privs` for `OW_BILLING` includes `CREATE TABLE` and `CREATE PROCEDURE`: the only usable account is the write-capable schema owner. |
| A3 | Atlas cluster admin API (project, cluster, db-user, access list read/write) | VERIFIED | `make tp-preflight PLATFORM=atlas`, 8 probes, 0 denied → `.tp-preflight/atlas-capabilities.json` |
| A4 | Atlas data write to `ow_billing_migration` | VERIFIED | temporary doc inserted, read back, dropped; `MONGODB_ATLAS_URI` |
| A5 | VM egress IP on the Atlas access list | VERIFIED | preflight `vm-ip-listed` |
| A6 | GitHub push + PR to `tp-run/mongodb-20260915T045208Z` | VERIFIED | branch cut from `tech-partnerships` and pushed |
| A7 | Source DSN secret `ORACLE_BILLING_URI` | **UNKNOWN — not provisioned in this org** | secret list has no `ORACLE_BILLING_URI`. The fixture Oracle is local to the VM with a fixture-local credential; no org secret is needed for the parent. Children get the fixture copy's DSN in their brief, never the live source. |
| A8 | Child VM → this VM's Oracle fixture | **DENIED (by design)** | children run on separate VMs with no route to `localhost:52521`. Children run `--mode fixture`; the parent owns the one live recon run. |

## A2 — the read-only question, on record

The engagement rule "source access is read-only" (AGENTS.md rule 1) **cannot be enforced by
grants here**. There is no read-only Oracle user and creating one would itself be a write to
the source. So read-only is enforced by discipline plus mechanics:

- every source statement is `SELECT`/`WITH` only; no DDL, DML, `MERGE`, or `ALTER SESSION`
  that changes data;
- the recon harness's Tier-4 replay is restricted to `SELECT`/`WITH`;
- writes go only to `ow_billing_migration` (`allowed_targets.json`);
- the fixture is re-seedable from `make oracle-billing-seed NS=demo` (seed 714559852), so a
  violation is detectable by re-running the seed and comparing the manifest.

Accepted as a risk at STOP A. Carried as `D4-1` in the dependency register.
