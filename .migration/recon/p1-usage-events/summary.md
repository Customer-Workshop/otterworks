# p1-usage-events (U-18, wave 1 / batch w1-b) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
Not an official harness verdict: D10-01 was denied, so Oracle is read over JDBC with a
repo-local source adapter while every tier, tolerance and canonicalization rule stays the
harness's own. See `DEGRADED.md`, `result.json`, `recon.summary.md`.

Unit: `OW_BILLING.USAGE_EVENTS` (814 rows) → `ow_tp.silver.usage_events`, analytical Delta
track, depth `full`, mode `live`, mapping `map-p1-v1`, tolerances `v1`, seed 0.

## What the gate compared

| tier | checks | result |
|---|---|---|
| 1 counts through mapping | 1 | PASS — source 814, target 814 |
| 2 per-field aggregates | 5 | PASS — `id`/`tenant_id` deferred to tier 3 |
| 3 keyed diffs | 814 | PASS — full diff on the whole population, 0 null keys, 0 duplicate source keys |
| 4 app-level parity (ops) | 3 | PASS |

Tier-4 ops (`databricks/migration/recon/ops/p1_usage_events_ops.json`), source side in
Oracle dialect with quoted lower-case aliases, target side recomputed from Delta:

- `usage_units_by_tenant_period` — `SUM(units)` and row count grouped by `tenant_id` and
  the `YYYY-MM` period of `occurred_at`. This is the baseline wave 3 needs before
  `pkg_rating`'s cursor arithmetic is converted: **69 tenant/period groups, one period
  (`2026-02`), 336,293 units over 814 events.**
- `usage_kind_cd_is_a_known_usage_kind` — 0 rows on both sides whose `kind_cd` is not a
  `USAGE_KIND` code.
- `usage_units_are_positive` — 0 rows on both sides with a null or non-positive `units`.

## Fixture first

`fixture/` holds the fixture-mode run against the local Oracle fixture (10 rows),
**development evidence only, not a merge verdict**. The live run above is the single
merge-evidence run; the cap of 3 was not reached.

The first fixture run FAILED on tier 3 and the failure was real: `occurred_at` was landed as
Databricks `TIMESTAMP`, which is an instant rendered in the session zone, against an Oracle
`TIMESTAMP` that carries no zone. The column was changed to `TIMESTAMP_NTZ` — the mapping's
`TIMESTAMP` under P1-D3, where UTC is assumed and declared rather than applied as a
conversion. No tolerance or canonicalization rule was touched.

## Trigger enforcement

`TRG_USAGE_EVENTS_CHECK` is carried in two places, documented in
`databricks/migration/silver/usage_events_enforcement.md`:

- `units > 0` (ORA-20001) → Delta CHECK constraint `usage_events_units_positive` on
  `ow_tp.silver.usage_events`, so it binds every writer. Verified against the live table: an
  insert with `units = 0` is rejected with `DELTA_VIOLATE_CONSTRAINT_WITH_VALUES`, and the
  table stayed at 814 rows.
- `kind_cd` must exist in `CODES` where `code_type = 'USAGE_KIND'` (ORA-20002) → load-time
  expectation in `usage_events_extract.py`, evaluated against the code set read in the same
  read-only transaction as the rows. A Delta CHECK cannot look a value up in another table,
  and freezing today's codes into a literal list would enforce a different rule.

Both are also compared by the tier-4 ops above, so the gate re-proves them from the target.

## Idempotency

Proven by rerun, not inferred. The load was rerun over the same snapshot and the target
state was digested from the target platform both times
(`databricks/migration/transport/target_state_digest.py`, SHA-256 over sorted per-row
SHA-256 hashes): 814 rows,
`47e909dc86b56b5665d13872676e50d6ad1c6c049dedf59f2ce0b441cb99c7c6`, identical
(`idempotent: true`). The merge is a complete snapshot — keys absent from the source are
deleted — so it converges rather than accumulating.

## Source access

One live read of the legacy estate for this unit: `usage_events_extract.py` under
`with_oracle_secret.py`, a single `SET TRANSACTION READ ONLY` transaction covering both the
table and the `USAGE_KIND` code set. No DDL, no DML, no CDC enablement. Development ran
against the local fixture. Secrets are referenced by name only.

## NOT DATA-PROVEN / unverified paths

- Tiers 5–7 (source-side constraint, index and identity parity): the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. The Oracle primary
  key on `id` is carried as the merge key and is proven only by the tier-3 full diff finding
  no duplicate source keys, not by comparing catalog metadata.
- The foreign key `USAGE_EVENTS.TENANT_ID → TENANTS.ID` is not enforced on Delta: `TENANTS`
  is not a declared target of this unit, so there is nothing on the target side to reference.
  Orphans are reproduced, not cleaned (D8-01).
- The trigger's `BEFORE INSERT` per-row timing is not reproducible on a bulk MERGE. The
  rules are evaluated over the snapshot before the write: for a clean load the outcome is
  identical, for a dirty one Oracle rejects a row and this loader rejects the batch.
- `kind_cd` validity is enforced at load time, not by a constraint, so a future writer that
  bypasses the loader can insert an unknown kind. The tier-4 op is what detects that.
- `source_principal_read_only` is `unverified` in the factory doctor: it has no privilege
  query for the Oracle family. Confirmed by hand instead, read-only, and recorded here — the
  source principal holds `CREATE SESSION`, `SELECT ANY TABLE`, `SELECT ANY DICTIONARY` and
  `FLASHBACK ANY TABLE`, no roles and no object grants on `OW_BILLING`, so it cannot write.
  The doctor row stays unverified because the check itself is not implemented, not because
  the grants are unknown. Every other doctor row is `ok`, including `hook_platform_loaded`
  (nonce probe blocked) — the guard is live and blocked three commands during this unit.
- Machine-readable schema: this unit uses the harness's own `result.json`, as wave 0 did.
  No `*.recon.json` / `"kind": "recon-report"` artifact is produced, because the harness
  does not emit that schema; `result.json` is the machine-readable evidence.
