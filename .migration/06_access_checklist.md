# 06_access_checklist

## Environment fix (user-mandated, run once, 2026-09-26)
Command (as given at intake):
```
~/.venvs/recon/bin/python -m pip install -U pip setuptools && \
~/.venvs/recon/bin/python -m pip install -e "$(ls -d /opt/.devin/plugins/cache/*mongo-migration-plugin*/*/skills/mongo-recon-harness/harness | head -1)[all,test]" && \
~/.venvs/recon/bin/recon selftest
```
Outcome: **PASS**. `pip 26.2.1`, `setuptools 84.0.0` installed; editable install of
`mongo-recon-harness 0.3.2` from
`/opt/.devin/plugins/cache/github.com_Cognition-Partner-Workshops_mongo-migration-plugin-6d021e15/0.3.0/skills/mongo-recon-harness/harness`;
`recon selftest PASS: 9 canonicalization rules exercised` (exit 0). `recon --version` is not a
subcommand (only `selftest`, `run`); version taken from `pip show`.

## Local tooling
| Item | Result |
|---|---|
| Docker daemon | WORKS (server 29.7.2) |
| `mongo:7` image | present locally, nothing pulled |
| `container-registry.oracle.com/database/free:latest` | present locally (fixture source for playbook 2) |
| Python 3 + plugin scripts (`connectivity_probe.py`, `offline_guard.py`, `ddl_census.py`, `model_proposal.py`, `model_patch.py`) | present |

## Connectivity probe (playbook 1 step 5)
```
python3 skills/mongo-migration/connectivity_probe.py --policy offline --family oracle \
  --source-dsn-secret ORACLE_RO_DSN --target-db ow_billing_migration
→ source: ddl_only (policy_offline)
→ target: local (policy_offline)
```
(`ORACLE_RO_DSN` is a placeholder name; no such secret exists and none is read under `offline`.)

| Side | Status | Detail |
|---|---|---|
| Source (Oracle `OW_BILLING`) | NOT APPLICABLE (policy `offline`) | `source_access = ddl_only`; DDL from `services/legacy-billing/db/oracle/` |
| Target (migration cluster) | NOT APPLICABLE (policy `offline`) | `target_access = local`; `MONGO_LOCAL_URI=mongodb://localhost:27017`, db `ow_billing_migration` |
| Cutover principal | not held, by design | customer DBA (not present) |

## Offline guard
```
MONGO_LOCAL_URI=mongodb://localhost:27017 python3 skills/schema-modeling/offline_guard.py --repo . --source ddl_only --target local
→ exit 1: "MONGODB_ATLAS_URI is set (often inherited from the org environment) ... Run every offline command as `env -u MONGODB_ATLAS_URI <command>`."
MONGO_LOCAL_URI=mongodb://localhost:27017 env -u MONGODB_ATLAS_URI python3 skills/schema-modeling/offline_guard.py --repo . --source ddl_only --target local
→ offline guard: OK (source=ddl_only target=local MONGO_LOCAL_URI checked)
```
Standing rule for this engagement: every offline command runs under `env -u MONGODB_ATLAS_URI`.

## Tool refusals recorded
- Writing `.migration/allowed_targets.json` with only `{"databases": [...]}` caused the
  co-installed **dbx-migration-factory** PreToolUse hook to reject every subsequent file-edit
  and shell tool call in the repo: `dbx-migration-factory guard: cannot read
  .migration/allowed_targets.json: allowed_targets.json must contain a non-empty 'catalogs'
  list`. Resolution (D-000a): the file carries a `catalogs` key mirroring the single
  `databases` entry. No target was widened.

## Access model (three tiers)
| Tier | Purpose | Secret name | Status in this engagement |
|---|---|---|---|
| 1 Assessment read-only | read Oracle catalog/data | (none) | not provisioned; offline policy |
| 2 Migration write | write to `ow_billing_migration` on the migration cluster | (none; local `MONGO_LOCAL_URI` only) | local container only |
| 3 Cutover | production repoint | held by customer DBA | never requested by Devin |

Audit: session activity is visible in the Devin session log
(`https://partner-workshops.devinenterprise.com/sessions/983733d4647d4ea2b1fd4344adfa7b65`) and in the run branch's commit history.

## BLOCKED items
None at STOP A. `offline` policy makes source and migration-cluster access NOT APPLICABLE rather than BLOCKED; the consequence (no merge evidence, STOP C cannot be authorized from this session) is recorded in `02_tolerances.md` and D4-1/D4-2.
