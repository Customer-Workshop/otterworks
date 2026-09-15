# p1-invoices (U-06, wave 3 / batch w3-b) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter (`databricks/migration/recon/oracle_jdbc_adapter.py`); every
tier, tolerance and canonicalization rule is still the harness's own. See `DEGRADED.md`,
`result.json`, `recon.summary.md`.

Merge-evidence run: `--mode transactional --depth full --seed 0`, against the live source.
Fixture runs (`fixture/`) came first and are development evidence only, never a merge
verdict. Three full runs used of the three-run cap: two fixture runs (the first failed on
the `issued_at` type, below) and this one.

## What was compared

`OW_BILLING.INVOICES` (3 rows, the modern invoice generation — D9-01, not legacy
`INVOICE_HEADER`) against `billing.invoices` on Lakebase branch `mig-p1-w2`, through
`.migration/units/p1-invoices/mapping_spec.json`.

| tier | result | scope |
|---|---|---|
| 0 consistency_window | PASS | source snapshot vs target repeatable_read, held |
| 1 counts_through_mapping | PASS | 3 = 3 |
| 2 per_field_aggregates | PASS | 8 checks |
| 3 keyed_diffs | PASS | 3 keys, full diff, zero mismatches |
| 5 pk_set_diff | PASS | 3 keys |
| 6 cdc_lag_ordering | PASS | `issued_at` watermark, 1 check |
| 7 schema_parity | PASS (0 checks) | source metadata unreadable over JDBC — see below |

Target values are read back from Lakebase by the harness, never from the loader's output.

## Conversion decisions this evidence covers

- `subtotal`, `tax`, `total` are `NUMBER(12,2)` → `numeric(12,2)`, compared exactly. The
  loader sets `oracledb.defaults.fetch_decimals = True`, so money never becomes a float.
- `status_cd` is `NUMBER(4)` → `smallint` and stays a magic number (40 and 20 both appear in
  the source); no check constraint or lookup was added on either side.
- `issued_at` is zoneless on both sides (see the derived dialect rule below), UTC assumed
  and declared (P1-D3).
- `pk_invoices` and `fk_inv_tenant` are recreated under their Oracle names. The source has
  no orphan invoice (checked: 0 rows with a missing tenant and 0 with a missing period), so
  recreating the tenant FK does not collide with D8-01.
- `fk_inv_period` is **not** recreated: its parent `RATING_PERIODS` belongs to the
  concurrently running rating unit and is not on this branch. Creating another unit's table
  to hang the constraint on would be a write outside this batch's declared targets. The
  `period_id` values are carried across unchanged; the constraint is a wave-gate item.

## Derived dialect rule (skill_feedback)

The mapping spec gives `issued_at` the target type `timestamptz`. That cannot hold: Oracle
`TIMESTAMP` is zoneless, and the canonicalization file applies `identity` to
`TIMESTAMP(n>3)`, so a `timestamptz` column is read back tz-aware and every row is a Tier-3
`field_diff` against the naive source value. The first fixture run failed exactly that way
on all 3 rows. The column is therefore `timestamp`; the instant is unchanged. Wave 0 made
the same correction for `billing.billing_audit_log`
(`databricks/migration/lakebase/w0a_pkg_ow_util.sql:127`), so this is the second occurrence
and belongs in the Oracle→Lakebase dialect rules: **Oracle `DATE`/`TIMESTAMP` → Postgres
`timestamp`/`timestamp(0)`, never `timestamptz`, whatever the mapping spec's literal
`target_type` says.**

## Idempotency

Proven by rerun, not inferred. The loader ran against the fixture, then live, then against
the fixture again, reporting `source_rows=3 target_rows=3 deleted=0` every time. The target
was digested from Lakebase before and after the final rerun and did not move:

    rows=3 sha256=8f4b8bee8d1924812202a0944802b92bdf356e7c82e6bc51ca82273020cc70a5

The fixture and the live source hold the same three invoices (compared value by value, only
Oracle's `149` vs Postgres's `149.00` rendering differs), so the rerun could not have
replaced merge evidence with fixture data.

## NOT DATA-PROVEN / unverified paths

- Tiers 5–7 source-side metadata (constraints, indexes, identity): the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. That is also why
  `merge_eligible` is `false` — structural on this route, not a failure of this unit.
- `fk_inv_period` parity: nothing on the target enforces it yet (see above), so no evidence
  covers it. It is a wave-gate item once the rating unit merges.
- `source_principal_read_only` is `unverified` in the capability preflight: the doctor has no
  privilege query for the Oracle family. This unit used the read-only credential
  (`ow-tp/oracle/ow_billing_ro`) and issued no DDL or DML against Oracle, but the grants
  themselves were not machine-checked.
- `lakebase_branch_create` is `fail` in the same preflight because the shared parent branch
  `mig-p1-w2` carries an expiry. The branch exists and was used as it is; it was not
  created, reset or re-branched.
