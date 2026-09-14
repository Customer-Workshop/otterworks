# STOP B: choose the first pipeline

Date 2026-09-14. Stop mode soft (default accepted after 60 s unless replied). Inventory: `docs/migration/OW_BILLING_inventory.md` (DAG `docs/migration/OW_BILLING_lineage_dag.png`), governance `.migration/08_governance_inventory.md`, raw evidence `.migration/evidence/census/`.

## What the inventory found

- 69 objects, all VALID, census matches the intake and the repository DDL exactly (coverage VERIFIED, every object in exactly one of P1 / P2 / P3 / shared / excluded).
- Three pipelines: **P1 Monthly invoicing** (PKG_RATING, PKG_INVOICING, PKG_PLANS; 8 tables; 504 PL/SQL lines; rank 1), **P3 Customer master + legacy reporting copies** (202k rows, 37 orphans, EAV, 3 triggers; rank 2), **P2 Dunning** (PKG_DUNNING, 2 tables, disabled nightly job; rank 3). Shared wave-0 set: TENANTS, PLANS, CODES, BILLING_AUDIT_LOG, PKG_OW_UTIL.
- P2 depends on P1 (INVOICES, SUBSCRIPTIONS). P3 has no FK into the billing core.
- Parent facts confirmed live: ARCHIVELOG, supplemental logging MIN, ALL COLUMN logging on the 10 operational tables, `C##DBZUSER` open with the LogMiner grant set.

## New register rows (all UNDECIDED, decided at STOP C unless noted)

- **D10-8** the read-only principal cannot run `AS OF SCN` queries (no `FLASHBACK ANY TABLE`). Recon source pins fall back to per-session read-only transactions. One grant fixes it; customer DBA / parent.
- **D4-5** no production application in the repo calls the invoicing packages; the only callers are the parity harness and a disabled scheduler job. The customer's application inventory is needed to scope the STOP E repoint (question below).
- **D3-1** no producer for `USAGE_EVENTS` (the rating feed) exists in the repo.
- D4-2/3/4, D6-1/2, D7-1, D9-1, D2-2: consumer, shared-write, hand-off, sequence and dual-track rows.

## Decision

Which pipeline to analyse and migrate first.

**Recommendation: P1 Monthly invoicing** (wave 0 shared set first, then P1). It is the parent's mandate for this session, it is the hardest (money, three packages, trigger side effects, transactional recon), and P2 is blocked behind it anyway.

Exact reply that approves: `Approve STOP B: first pipeline P1 Monthly invoicing.`

Optional in the same reply (otherwise carried as UNDECIDED to STOP C): the external application(s) that call `PKG_PLANS`/`PKG_RATING`/`PKG_INVOICING` and the producer of `USAGE_EVENTS`; whether to grant `FLASHBACK ANY TABLE` to `OW_BILLING_RO`.
