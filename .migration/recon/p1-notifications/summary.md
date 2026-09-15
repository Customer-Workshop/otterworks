# p1-notifications (U-10) — recon verdict: PASS, grade DEGRADED

**DEGRADED — not an official harness verdict** (reason `d10_01_denied`,
`official_verdict=false`). The Oracle side is read over JDBC with the repo-local adapter,
which is outside the harness's tested matrix. See `DEGRADED.md`; the harness's own summary
is `recon.summary.md`.

## What ran

- Fixture first (`--mode fixture --depth full`, PASS, evidence under `fixture/`, never
  merge evidence), then exactly one merge-evidence run
  (`--mode transactional --depth full --seed 0`).
- Tiers 0–3 and 5–6 PASS. Source-side constraint, index and identity parity (tiers 5–7) is
  **unverified** on the JDBC route.
- Idempotency: two loads, two digests (`load_digest_run1.json`, `load_digest_run2.json`),
  identical row count and content hash read back off Lakebase.
- Recon values are recomputed from Lakebase and Oracle directly.

## Conversion notes

- `sent_at` is `timestamp(6)`, and the mapping spec now says so too: the generator's
  `timestamptz` was accepted as a dialect finding and corrected in ledger entry D-010, so
  this unit's DDL and its spec agree. The source column is a zone-less Oracle `TIMESTAMP`;
  UTC is assumed and declared (P1-D3), so the target keeps the zone-less type at the
  source's own precision.
  The fixture run proved the point before the type was changed: a `timestamptz` target
  returned `2026-02-16 09:00+00` against a source `2026-02-16 09:00`, and the run failed,
  because the canonicalization profile applies `datetime_utc_truncate_ms` to
  `TIMESTAMP → TIMESTAMP_NTZ` only — a zoned target is compared under `identity` and never
  equals the zone-less source value. Tolerances were not retuned; the target type was
  corrected. The generator (`databricks/migration/tools/gen_mapping_specs.py`) and the six
  frozen specs were fixed by the wave-close change this branch is rebased on, not here.
- `uq_notifications (tenant_id, kind_cd, sent_at)` is declared: it is the dedupe key
  `sp_suspend_overdue` reads with `NOT EXISTS`, which is what makes a second sweep on the
  same day write nothing.
- No foreign key to `tenants`: orphan rows are reproduced, not cleaned (D8-01).
- Kind codes stay magic numbers (1 invoice, 2 dunning, 3 suspension).

## Evidence

| File | What it is |
|---|---|
| `result.json` | the harness result, with the degraded block |
| `p1-notifications.recon.json` | machine-readable report (`kind: recon-report`) |
| `recon.summary.md`, `report.md` | the harness's own summary and report |
| `DEGRADED.md` | why this is not an official verdict |
| `load_digest_run1.json`, `load_digest_run2.json` | the rerun that proves idempotency |
| `fixture/` | the fixture run, development evidence only |
