# 06 — Access checklist and model

## Capability checklist (probed 2026-09-01, this VM)

| Capability | Principal / secret | Status | Evidence |
|---|---|---|---|
| Read Oracle source (host side) | Assessment / fixture DSN `localhost:52521/FREEPDB1` user `ow_billing` | WORKS | python-oracledb `SELECT 1 FROM dual` → 1 |
| Read Oracle source (in-container sqlplus) | Assessment | WORKS | Seeded counts verified: 25,000 / 18,750 / 150,000 / 8,333 / 60 |
| Read Atlas project + cluster | Migration / Atlas API keys | WORKS | HTTP 200; project `otterworks-demos`; cluster `otterworks-demo` MongoDB 8.0.29, unpaused |
| Read Atlas access list | Migration / Atlas API keys | WORKS | HTTP 200; VM egress IP 140.232.64.2 already covered — no temporary entry created |
| Write migration database | Migration / `MONGODB_ATLAS_URI` | WORKS | `ow_tp_mongodb_032752._capability_probe`: insert/read/delete/drop all acknowledged; negative residue check clean |
| Sample-data approval | Deterministic seeded fixture (NS=demo) | WORKS | Provisioned per repo runbook; no real customer data |
| Production repoint | Customer-held cutover principal | NOT REQUESTED | Required only after STOP C; Devin never holds it |

No BLOCKED items. No access requests outstanding.

## Access model (one page, for the security reviewer)

### Principal tiers

1. **Assessment** — Oracle source access, SELECT-only in behavior, used for census and
   reconciliation. Fixture-local dev credential; no schema, data, grant, user, job, or
   configuration change is ever made on the source.
2. **Migration** — Atlas data plane via `MONGODB_ATLAS_URI` (writes limited to targets
   registered in `04_progress.md`, all inside `ow_tp_mongodb_032752*`), and Atlas control
   plane via `MONGODB_ATLAS_PUBLIC_KEY` / `MONGODB_ATLAS_PRIVATE_KEY` /
   `MONGODB_ATLAS_PROJECT_ID` (read + access-list management only; no cluster changes).
3. **Customer-held cutover** — owns production configuration/DNS/feature-flag repoint and
   rollback. Never requested, stored, or exercised by Devin.

### Audit attribution

Devin activity is attributable through the Atlas API key / database-user audit identity,
the unique run branch, the isolated `ow_tp_mongodb_032752*` databases, the `ns` field on
every migrated document, PR history on the run branch, and recon artifacts carrying unit,
mapping version, tolerance version, mode, seed, and watermark.
