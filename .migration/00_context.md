# 00 Context — OW_BILLING → MongoDB Atlas

Engagement facts. Source of truth for every later session and every fan-out child.
Marks: FACT (from the intake form or probed), PROPOSED (defaulted, confirmed at a stop).

## Source

| Field | Value | Mark |
|---|---|---|
| Source family | `oracle` (profile `profiles/oracle.md`) | FACT |
| Version | Oracle Database Free 23c, PDB `FREEPDB1`, schema `OW_BILLING` | FACT |
| Host | `localhost:52521` from the VM; `localhost:1521` inside container `otterworks-oracle-billing-oracle-billing-1` | DISCOVERED |
| Size | 20 tables, 4 PL/SQL packages, ~200 MB | FACT |
| Headline counts (NS=demo, seed 714559852) | CUSTOMER_MASTER 25,000 (155 cols) / INVOICE_HEADER 18,750 / INVOICE_LINE 150,000 / ENTITY_ATTR_VALUE 8,333 / TENANTS 60 per-ns | DISCOVERED |
| Other readers/writers | billing-service, the CUSTBILL batch chain, the parity harness | FACT |
| Source DSN env var | `ORACLE_BILLING_URI` (fixture-local credential, not an org secret — see `06_access_checklist.md`) | PROPOSED |

## Target

| Field | Value | Mark |
|---|---|---|
| Atlas project / cluster | `otterworks-demos`, existing free-tier M0 | FACT |
| Migration database | `ow_billing_migration` (the only allowed write target) | FACT |
| Scale | demo only — M0 gives 512 MB storage | FACT |
| Target credential | secret `MONGODB_ATLAS_URI` | FACT |
| Drivers | Java 17 (MongoDB Java driver 5.x); Python 3.12 loaders | FACT |

## Repo and branch

| Field | Value | Mark |
|---|---|---|
| Repo | `Cognition-Partner-Workshops/otterworks` | FACT |
| Working branch | `tp-run/mongodb-20260915T045208Z`, cut from `tech-partnerships` | PROPOSED (STOP A) |
| PR rule | one PR per unit into the working branch; must pass `make tp-smoke` | FACT |
| Workspace | `.migration/` at repo root | FACT |
| Target data model | the attached PRD, v1.0 — binding. The mapping spec implements it and adds nothing it does not decide. Its `Open` items are answered from the PL/SQL packages with evidence at STOP B. | FACT |

## Process

| Field | Value | Mark |
|---|---|---|
| `stop_mode` | `soft` (60-second default-accept), **STOP B hard** by request, **STOP C always hard** | FACT |
| Stop routing | this Devin session only | FACT |
| Notifications | STOP A/B/C, wave close, halt. Nothing else (AGENTS.md rule 9). | FACT |
| Fan-out width | 4 (one child per unit in wave 1) | FACT |
| Child source reachability | children run on their own VMs and **cannot** reach this VM's Oracle fixture. Children develop and self-verify against a fixture copy (`run_mode: fixture`); the parent runs the single live recon. | DISCOVERED |
| PR reviewer | the requester, same-day turnaround | FACT |
| Cutover principal | held by the requester. Devin never holds it. | FACT |
| Rollback owner | the requester, decides within 24h of cutover | FACT |

## Standing constraints (from the engagement request)

1. The PRD is the target. No collection or field the PRD does not call for.
2. Read-only on the source is a discipline, not a grant — the fixture has only the schema
   owner. See `06_access_checklist.md` D4-1.
3. One PR per unit into `tp-run/mongodb-*`; `make tp-smoke` green is a merge condition.
4. Seeded bad data is frozen at 37 orphan invoice lines, 50 dirty `SIGNUP_DT`, 31 malformed
   CSV lists (`testdata/legacy/manifests/demo.json`). Recon must find exactly those. More is
   a finding, never a tolerance change.
5. `make tp-preflight PLATFORM=atlas` runs before wave 1 and its manifest goes in every
   child brief.
