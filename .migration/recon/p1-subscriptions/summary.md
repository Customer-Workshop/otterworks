# p1-subscriptions (U-03, wave 2 / batch w2-a) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter (`databricks/migration/recon/oracle_jdbc_adapter.py`); every
tier, tolerance and canonicalization rule is still the harness's own. See `DEGRADED.md`,
`result.json`, `recon.summary.md`.

Merge-evidence run: `--mode transactional --depth full --seed 0`, one live source read.
A fixture run (`fixture/`) came first and is development evidence only, never a merge
verdict. Two full runs used of the three-run cap.

## What was compared

`OW_BILLING.SUBSCRIPTIONS` (69 rows) against `billing.subscriptions` on Lakebase branch
`mig-p1-w2`, through `.migration/units/p1-subscriptions/mapping_spec.json`.

| tier | result | scope |
|---|---|---|
| 0 consistency_window | PASS | source snapshot vs target repeatable_read |
| 1 counts_through_mapping | PASS | 69 = 69 |
| 2 per_field_aggregates | PASS | 7 columns |
| 3 keyed_diffs | PASS | 69 keys, full diff, zero mismatches |
| 5 pk_set_diff | PASS | 69 keys, 66 ranges |
| 6 cdc_lag_ordering | PASS (0 checks) | no watermark declared for this unit |
| 7 schema_parity | PASS (0 checks) | source metadata unreadable over JDBC — see below |

Target values are read back from Lakebase by the harness, never from the loader's output.

## Conversion decisions this evidence covers

- Oracle `DATE` keeps its time part: `starts_on`, `ends_on`, `suspended_on` are
  `timestamp(0)`, never `date` (P1-D3, UTC assumed and declared).
- `status_cd` is `NUMBER(4)` → `smallint` and stays a magic number (10 active, 20 suspended,
  30 cancelled); no lookup table is introduced.
- The Oracle foreign keys `fk_sub_tenant` and `fk_sub_plan` are deliberately **not**
  recreated. D8-01 requires orphan rows to be reproduced, and a foreign key would reject
  them on load.
- `TRG_SUB_NO_UNCANCEL` is reproduced as a `BEFORE UPDATE OF status_cd` row trigger that
  silently rewrites `status_cd` back to 30. The Oracle trigger raises nothing, so neither
  does this one; the observable behaviour is the rewrite, not an error. Proven by the
  un-cancel probe in `../p1-pkg-plans/behaviour_check.json` (`trg_sub_no_uncancel`: no
  exception raised, status stays 30 on both platforms).

## Idempotency

Proven by rerun, not inferred: the loader was run again unchanged against the same target
and reported `source_rows=69 target_rows=69 deleted=0` both times, and the live load after a
fixture load also reported `deleted=0` (identical key sets). The loader deletes target keys
the source no longer has before upserting, so a rerun converges rather than accumulating.

## NOT DATA-PROVEN / unverified paths

- Tiers 5–7 source-side metadata (constraints, indexes, identity): the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. That is also why
  `merge_eligible` is `false` — structural on this route, not a failure of this unit.
- `SUBSCRIPTIONS_HIST` and `TRG_SUBSCRIPTIONS_HIST` are out of this unit's declared write
  targets; the history rows Oracle writes on every subscription update have no target rows
  until that unit lands.
- No CDC watermark is declared for this table, so tier 6 ran zero checks.
