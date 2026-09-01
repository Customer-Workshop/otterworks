# 00 — Engagement context

## Engagement

| Field | Value | Status |
|---|---|---|
| Goal | Migrate the entire OtterWorks Oracle billing estate to MongoDB Atlas | FACT — user requested 2026-09-01 |
| Source family | `oracle` | FACT |
| Source profile | mongo-migration plugin `profiles/oracle.md` (v0.2.0) | FACT |
| Source repository | `Cognition-Partner-Workshops/otterworks` | FACT |
| Run branch | `tp-run/mongodb-20260901T032752Z` (cut from `tech-partnerships`) | FACT |
| Run namespace | `mongo_032752` | PROPOSED |
| Current phase | Phase 1 — setup, STOP A pending | FACT |
| Recon mode | LIVE dual-connection reconciliation | PROPOSED |
| Source schema | `OW_BILLING` plus every application SQL/procedure touchpoint | PROPOSED |

No migration, inventory, modeling, or cutover work is authorized before the applicable
recorded stop approval.

## Source topology

- Source estate: Oracle Free (FREEPDB1), schema `OW_BILLING`, reachable from this VM at
  `localhost:52521/FREEPDB1` (container-internal 1521).
- The estate was provisioned this session per the repository runbook
  (`make oracle-billing-up` + `make oracle-billing-seed NS=demo`, deterministic seed) and
  is treated strictly READ-ONLY from that point forward. Seeded facts (verified via
  sqlplus): CUSTOMER_MASTER 25,000 rows (155 columns); INVOICE_HEADER 18,750;
  INVOICE_LINE 150,000 (37 known orphans); ENTITY_ATTR_VALUE 8,333; TENANTS 60 rows in
  the `demo::` namespace (shared table also carries 9 static baseline rows).
- Host-side read access verified with python-oracledb (`SELECT 1 FROM dual` → 1).

## Interaction contract

- STOPs A, B, and C are routed as blocking decisions in this Devin session.
- Questions are batched into the relevant STOP; silence is never approval.
- The requesting user approves STOP A and STOP B.
- STOP C additionally requires the named customer cutover owner and a fresh cutover window.
- No external notification route is configured; chat-only notifications are PROPOSED.
- Production repoint execution is customer-held. Devin never requests or uses that principal.

## Scope posture

The candidate scope is the entire `OW_BILLING` schema plus every repository code path that
reads it or invokes its stored logic. Phase 2 must census the full candidate scope and put
every object into exactly one approved bucket; this file does not pre-exclude any table,
package, trigger, sequence, job, or application path.

## Loaded method

- Migration method: `mongo-migration` skill
- Reconciliation authority: `mongo-recon-harness` skill (its `result.json` verdict is the
  only merge gate; nothing self-certifies)
- Source-specific profile: Oracle
- Profile `recon_canonicalization` rules are passed to the harness verbatim as data, with
  the `SET_AT_STOP_A` placeholders resolved from the approved tolerance record.
