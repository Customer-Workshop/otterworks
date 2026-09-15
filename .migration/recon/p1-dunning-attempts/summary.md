# p1-dunning-attempts (U-09) — recon verdict: PASS, grade DEGRADED

**DEGRADED — not an official harness verdict** (reason `d10_01_denied`,
`official_verdict=false`). The Oracle side is read over JDBC with the repo-local adapter,
which is outside the harness's tested matrix. See `DEGRADED.md`; the harness's own summary
is `recon.summary.md`.

## What ran

- Fixture first (`--mode fixture --depth full`, PASS, evidence under `fixture/`, never
  merge evidence), then exactly one merge-evidence run
  (`--mode transactional --depth full --seed 0`).
- Tiers 0–3 and 5–6 PASS. Tiers 5–7 constraint, index and identity parity on the **source**
  side are **unverified**: the JDBC adapter reads no constraint metadata under
  `d10_01_denied`. That is a property of the route, not of this unit. The two foreign keys
  below were therefore read from Oracle's `ALL_CONSTRAINTS` directly and checked back off
  Lakebase with `pg_get_constraintdef`, outside the harness.
- Idempotency: the load ran twice against the same source; `load_digest_run1.json` and
  `load_digest_run2.json` (row count plus an order-independent content hash, read back off
  Lakebase) are identical apart from run id and timestamp.
- Recon values are recomputed from Lakebase and Oracle directly, never from this unit's own
  load output.

## Conversion notes

- `NUMBER(4)` → `smallint`, `VARCHAR2(36)` → `varchar(36)`, and the Oracle `DATE`
  `scheduled_for` → `timestamp(0)`: the time part is kept, the source carries no zone, UTC
  is assumed and declared (P1-D3).
- `uq_dunning_attempts (invoice_id, attempt_no)` is declared. Oracle declares it too, but
  the scheduler's `MAX(attempt_no)+1` is what actually depends on it: without the
  constraint, a concurrent run would duplicate an attempt number instead of failing — and
  that failure is the one `WHEN OTHERS THEN NULL` swallows (P1-D2).
- Both Oracle foreign keys are recreated under their source names:
  `fk_da_tenant (tenant_id) -> billing.tenants(id)` and
  `fk_da_invoice (invoice_id) -> billing.invoices(id)`. Oracle's `ALL_CONSTRAINTS` gives
  `DELETE_RULE = 'NO ACTION'`, `NOT DEFERRABLE`, `IMMEDIATE`, `VALIDATED` for both, and
  Oracle has no `ON UPDATE` clause, so neither key carries a delete or update action here.
  An earlier revision left them out on a D8-01 reading; that was wrong. D8-01 reproduces
  orphan rows that exist in the source, and both keys are enabled and validated on Oracle,
  so no orphan can exist to reproduce. Confirmed on the target before the keys were added:
  zero rows in `billing.dunning_attempts` fail either reference.
- The DDL is rerunnable: each key is added inside a `DO` block guarded on `pg_constraint`,
  because Postgres has no `ADD CONSTRAINT IF NOT EXISTS` (P1-D6).
- Status codes stay magic numbers (10 scheduled, 20 sent, 30 skipped).

## Evidence

| File | What it is |
|---|---|
| `result.json` | the harness result, with the degraded block |
| `p1-dunning-attempts.recon.json` | machine-readable report (`kind: recon-report`) |
| `recon.summary.md`, `report.md` | the harness's own summary and report |
| `DEGRADED.md` | why this is not an official verdict |
| `load_digest_run1.json`, `load_digest_run2.json` | the rerun that proves idempotency |
| `fixture/` | the fixture run, development evidence only |
