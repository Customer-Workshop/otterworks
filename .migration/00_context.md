# 00 — Engagement context

Engagement: OtterWorks billing estate → MongoDB Atlas.
Playbook: mongo-migration 1 (Setup & Engagement Intake). Status: STOP A.

## Source family and profile

- Source family: **oracle** (exactly one profile is loaded for the whole engagement).
- Profile loaded: `skills/mongo-migration/profiles/oracle.md` (plugin
  `account-upload_org-default-8486a6b8` v0.1.1).
- Canonicalization block copied to `profile.canon.json` with the STOP A placeholders
  resolved.

## Scope

In scope — Oracle schema `OW_BILLING` only:

| Unit | Wave | Source objects | Target collection |
|---|---|---|---|
| `customers` | 1 | `CUSTOMER_MASTER` (155 cols, 25,000 rows) + `ENTITY_ATTR_VALUE` (8,333 rows) | `ow_tp_demo.customers` |
| `invoices` | 2 | `INVOICE_HEADER` (18,750 rows) + `INVOICE_LINE` (150,000 rows) | `ow_tp_demo.invoices` |

Wave order is dependency-ordered: `customers` lands before `invoices`, because invoice
documents carry the customer key that wave 1 establishes.

Out of scope — **declared coverage gaps**, not oversights:

| Excluded | Reason |
|---|---|
| `documents` unit (Postgres `otterworks_demo.documents` / `document_versions` / `document_snapshots`) | Postgres has no source profile; the method loads exactly one profile per engagement |
| `files` unit (DynamoDB `otterworks-file-metadata`) | DynamoDB has no source profile |
| The other 16 `OW_BILLING` tables (`SUBSCRIPTIONS`, `PLANS`, `USAGE_EVENTS`, `RATING_*`, `DUNNING_ATTEMPTS`, `CODES`, `TENANTS`, `NOTIFICATIONS`, `BILLING_AUDIT_LOG`, `CREDIT_NOTES`, `INVOICES`, `INVOICE_LINES`, `FIXTURE_META`, `*_HIST`) | Not in the two approved units; no mapping, no load, no recon coverage |
| 5 PL/SQL packages, 7 triggers, 5 sequences | Not converted in this engagement; `_HIST` triggers and sequences remain source-side |

## Census facts (probed, read-only, 2026-08-31)

All rows below are FACT — measured against the live source with the read-only-by-policy
principal. Everything not in this section is PROPOSED.

| Fact | Value |
|---|---|
| Schema | `OW_BILLING`, 20 tables |
| `CUSTOMER_MASTER` columns | 155 |
| Row counts | `CUSTOMER_MASTER` 25,000 / `ENTITY_ATTR_VALUE` 8,333 / `INVOICE_HEADER` 18,750 / `INVOICE_LINE` 150,000 |
| Orphaned `INVOICE_LINE` rows (no matching header) | 37 |
| Column types across the 4 in-scope tables | VARCHAR2 122, NUMBER 42, CHAR 25, DATE 2 |
| CLOB / BLOB / RAW / XMLTYPE / TIMESTAMP columns in scope | **none** |
| Database character set | `NLS_CHARACTERSET=AL32UTF8`, `NLS_NCHAR_CHARACTERSET=AL16UTF16` |
| Comparison semantics | `NLS_COMP=BINARY`, `NLS_SORT=BINARY`, `NLS_LENGTH_SEMANTICS=BYTE` |
| PL/SQL inventory | 5 PACKAGE + 5 PACKAGE BODY, 7 TRIGGER, 5 SEQUENCE |
| Source principal privileges | `OW_BILLING`: CREATE SESSION, TABLE, SEQUENCE, PROCEDURE, TRIGGER, VIEW, TYPE, JOB; no granted roles |

Consequences already fixed by these facts:

- No LOB tier is needed: no column in scope can approach the 16 MB document limit.
- `collation_casefold` stays **disabled** — the source compares binary, so case-folding
  would make recon accept a difference the source treats as real.
- `rstrip_spaces` **is** required: 25 blank-padded CHAR columns are in scope.
- `datetime_utc_truncate_ms` applies to 2 DATE columns only; there is no sub-millisecond
  precision to lose.

## Capability preflight manifest

Probed with the real credentials against the paths the later playbooks actually use.
"The credential authenticates" is not recorded as a pass anywhere below.

| Path | Result | Evidence |
|---|---|---|
| Source connect + `discovery_commands` query | **PROBED-OK** | `all_tables` / `all_tab_columns` / `all_objects` / `user_sys_privs` returned; census facts above |
| Source principal is read-only | **PROBED-GAP** | `user_sys_privs` shows CREATE TABLE / PROCEDURE / TRIGGER / SEQUENCE / TYPE / JOB. The principal **can** write. See gap G1 |
| Target connect | **PROBED-OK** | MongoDB 8.0.29 on `otterworks-demo.cgbijgv.mongodb.net` |
| Target scratch write + delete in the designated database | **PROBED-OK** | insert / read / delete / drop of `ow_tp_demo._migration_preflight`; nothing else on the cluster touched |
| Atlas control plane (project/cluster/db-user/access-list read, access-list POST + DELETE) | **PROBED-OK** | `make tp-preflight-atlas`, 8/8 probes verified, manifest at `.tp-preflight/atlas-capabilities.json` |
| VM IP present in the Atlas access list | **PROBED-OK** | covered by 4 existing entries |
| Recon harness install + selftest | **PROBED-OK** | `pip install -e ".[all]"` then `recon selftest`: PASS, 9 canonicalization rules exercised |
| `mongodb-mcp` points at the migration cluster | **PROBED-PARTIAL** | the plugin's `.mcp.json` sets `MDB_MCP_CONNECTION_STRING` by indirection to the `MONGODB_ATLAS_URI` name, so it resolves to the same cluster; no call was made through the server. The oracle profile delegates **no** concern to MCP (`mcp_delegation` is `reasoning` for every row), so no `mcp_delegation` row will use it this engagement |
| Load throughput at unit scale | **NOT PROBED** | no bulk load has been run; the 150,000-row embed path is unmeasured. See gap G4 |

## Open gaps

- **G1 — the source principal is write-capable.** `OW_BILLING` is the schema owner; no
  read-only principal exists in the estate (`setup/01_users.sql` creates only the owner)
  and there is no DSN secret NAME for it. Approved at STOP A to proceed as-is: read-only
  is enforced by **policy and review**, not by grants. Every source statement in this
  engagement is a `SELECT`; any other verb against `OW_BILLING` is a guardrail breach.
- **G2 — the harness has no empty-input guard.** `tier1_counts` compares
  `row_count(source)` against `doc_count(target)`; `0 == 0` passes and Tiers 2-3 then have
  nothing to diff, so an empty source table yields a *vacuous* PASS. The
  "empty source = FAIL" decision (D5) therefore cannot be enforced by the harness and is
  implemented as a pre-load precondition check in each unit's loader.
- **G3 — two canonicalization rules ignore their policy parameters.** In
  `recon/canon.py`, `_empty_string_is_null` always maps `"" -> None` and
  `_null_missing_equiv` always maps *missing* `-> None`, regardless of `params`. The
  policy values recorded in `profile.canon.json` are therefore the only ones the code can
  honor; selecting the opposite policy would require dropping the rule from a field's rule
  list rather than changing its params. Raised as PROFILE/HARNESS FEEDBACK.
- **G4 — load throughput is unmeasured.** With `source_concurrency = 1` against a
  single-container Oracle Free fixture, the wave-2 embed load (150,000 child rows) has no
  measured runtime. Sized at playbook 3, not guessed here.
- **G5 — `all_tables.num_rows` is empty on this source.** The profile's first discovery
  command returns NULL row estimates because optimizer statistics have never been
  gathered on the freshly seeded schema. Row counts above came from `COUNT(*)`. Raised as
  PROFILE FEEDBACK.

## Cutover principal

Customer-held. Devin never requests, holds, or stores it, and performs no production
repoint action. Recorded as confirmed at STOP A.
