# p1-invoices (U-06, wave 3 / batch w3-b) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter (`databricks/migration/recon/oracle_jdbc_adapter.py`); every
tier, tolerance and canonicalization rule is still the harness's own. See `DEGRADED.md`,
`result.json`, `recon.summary.md`.

Merge-evidence run: `--mode transactional --depth full --seed 0`, against the live source.
Fixture runs (`fixture/`) came first and are development evidence only, never a merge
verdict. This evidence is the re-run after `fk_inv_period` was added to the target (below);
each directed correction round used one fixture run and one merge-evidence run, inside the
three-run cap.

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
- `fk_inv_period` (`period_id` → `billing.rating_periods(id)`) is now recreated as well.
  Oracle declares it with no `ON DELETE` clause, so `USER_CONSTRAINTS.DELETE_RULE` is
  `NO ACTION` and it is `NOT DEFERRABLE`; Oracle has no `ON UPDATE`. The Postgres
  constraint keeps both defaults, so it is `NO ACTION` on delete and on update — not the
  cascade the child-side `fk_il_invoice` carries. The DDL adds it in a `DO` block guarded
  on `pg_constraint`, so re-running is a no-op, and only `billing.invoices` is written:
  `billing.rating_periods` is referenced, never created or altered. No invoice on either
  side points at a missing period, so the constraint rejects nothing.

## Dialect rule: D-010

`issued_at` is `timestamp(6)`. The unit's first version followed the mapping spec's original
`timestamptz` and every row failed Tier 3: Oracle `TIMESTAMP` is zoneless, the
canonicalization file applies `identity` to `TIMESTAMP(n>3)`, and a `timestamptz` column is
read back tz-aware, so it no longer equals the naive source value. Wave 0 had already made
the same correction by hand for `billing.billing_audit_log`
(`databricks/migration/lakebase/w0a_pkg_ow_util.sql:127`).

The owner has since settled it as ledger decision **D-010**: Oracle `TIMESTAMP` → Postgres
`timestamp(6)`, never `timestamptz`. The unit mapping spec and the spec generator
(`databricks/migration/tools/gen_mapping_specs.py`) now emit `timestamp(p)`, and this
evidence is the re-run against that corrected spec — DDL, target column and spec all agree.
The instant is unchanged and UTC stays the declared assumption (P1-D3).

## Idempotency

Proven by rerun, not inferred. The loader ran against the fixture, then live, then against
the fixture again, reporting `source_rows=3 target_rows=3 deleted=0` every time. The target
was digested from Lakebase before and after the final rerun and did not move:

    rows=3 sha256=8f4b8bee8d1924812202a0944802b92bdf356e7c82e6bc51ca82273020cc70a5

The DDL script was applied twice in a row when `fk_inv_period` was added; the second run
changed nothing, so the guarded `DO` blocks are idempotent in practice, not just by shape.

The fixture and the live source hold the same three invoices (compared value by value, only
Oracle's `149` vs Postgres's `149.00` rendering differs), so the rerun could not have
replaced merge evidence with fixture data.

## NOT DATA-PROVEN / unverified paths

- Tiers 5–7 source-side metadata (constraints, indexes, identity): the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. That is also why
  `merge_eligible` is `false` — structural on this route, not a failure of this unit.
- `fk_inv_period` parity is not covered by a harness tier: Tier 7 reads no source catalog
  metadata over JDBC. The constraint's shape and its `NO ACTION` delete rule were read from
  Oracle's `USER_CONSTRAINTS` / `USER_CONS_COLUMNS` directly and matched against
  `pg_constraint` on the target by hand; that check is metadata, not a harness verdict.
- `source_principal_read_only` is `unverified` in the capability preflight: the doctor has no
  privilege query for the Oracle family. This unit used the read-only credential
  (`ow-tp/oracle/ow_billing_ro`) and issued no DDL or DML against Oracle, but the grants
  themselves were not machine-checked.
- `lakebase_branch_create` is `fail` in the same preflight because the shared parent branch
  `mig-p1-w2` carries an expiry. The branch exists and was used as it is; it was not
  created, reset or re-branched.
