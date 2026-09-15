# p1-credit-notes (U-08, wave 2 / batch w2-f) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter (`databricks/migration/recon/oracle_jdbc_adapter.py`); every
tier, tolerance and canonicalization rule is still the harness's own. See `DEGRADED.md`,
`result.json`, `recon.summary.md`.

Merge-evidence run: `--mode transactional --depth full --seed 0`, one live source read.
A fixture run (`fixture/`) came first and is development evidence only, never a merge
verdict. Two full runs used of the three-run cap.

## What was compared

`OW_BILLING.CREDIT_NOTES` (5 rows) against `billing.credit_notes` on Lakebase branch
`mig-p1-w2`, through `.migration/units/p1-credit-notes/mapping_spec.json`.

| tier | result | scope |
|---|---|---|
| 0 consistency_window | PASS | source snapshot vs target repeatable_read, held |
| 1 counts_through_mapping | PASS | 5 = 5 |
| 2 per_field_aggregates | PASS | 5 columns |
| 3 keyed_diffs | PASS | 5 keys, full diff, zero mismatches |
| 5 pk_set_diff | PASS | 5 keys |
| 6 cdc_lag_ordering | PASS | `issued_on` watermark, 1 check |
| 7 schema_parity | PASS (0 checks) | source metadata unreadable over JDBC — see below |

Target values are read back from Lakebase by the harness, never from the loader's output.

## Conversion decisions this evidence covers

- `amount` and `remaining_amount` are `NUMBER(12,2)` → `numeric(12,2)`, compared exactly.
  The loader sets `oracledb.defaults.fetch_decimals = True`, so money never becomes a float.
- Oracle `DATE` keeps its time part: `issued_on` is `timestamp(0)`, never `date`
  (P1-D3, UTC assumed and declared).
- Both Oracle constraints are recreated under their Oracle names: `pk_credit_notes` and
  `fk_cn_tenant` (`tenant_id` → `billing.tenants(id)`, merged in wave 1). The source
  enforces that foreign key and holds no orphan credit note, so D8-01 is not in tension
  here. Nothing Oracle does not have was added.
- The only Oracle index on the table is the implicit unique index behind `PK_CREDIT_NOTES`;
  the Postgres primary key provides the same one, so no extra index was created.
- Ordering guarantee for wave 3's burn-down (`ORDER BY issued_on, id`, oldest first) is
  documented in `databricks/migration/lakebase/w2f_credit_notes.md`. The burn-down itself is
  not implemented here, and this unit wrote no other table — in particular not
  `billing.invoices` or `billing.invoice_lines`.

## Idempotency

Proven by rerun, not inferred: the loader ran twice against the fixture and once live,
reporting `source_rows=5 target_rows=5 deleted=0` every time. It deletes target keys the
source no longer has before upserting, so a rerun converges rather than accumulating.

Re-proven after the shared loader changed on this branch (`advance_sequence`, derived-field
and trigger handling, none of which this unit's mapping uses). The target's five rows were
read back with `compare_fixture_target.py`, the source's with `read_source_rows.py`, and
they matched, so a further load could only be a no-op; the loader then ran again and the
target digest was unchanged:

    rows=5 sha256=067460f700ce9ccc8ef5e8e9da95639703aa881944b357bcb3fa4fed3b777ba4

before and after. Both reads are of the target platform and the source, never of the
loader's own output, and the rerun used the fixture, so the one live read still stands at
one.

## NOT DATA-PROVEN / unverified paths

- Tiers 5–7 source-side metadata (constraints, indexes, identity): the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. That is also why
  `merge_eligible` is `false` — structural on this route, not a failure of this unit.
- `source_principal_read_only` is `unverified` in the capability preflight: the doctor has no
  privilege query for the Oracle family. The unit used the read-only credential
  (`ow-tp/oracle/ow_billing_ro`) and issued no DDL or DML against Oracle, but the grants
  themselves were not machine-checked.
- No `*.recon.json` (`"kind": "recon-report"`) is emitted. `emit_recon_report.py` recounts
  declared anomaly classes over `ow_tp.silver.*` on the SQL warehouse and reads two
  target-state digests of Delta tables, so it covers the Delta track; the Lakebase units
  (`p1-tenants`, `p1-plans`, `p1-codes`, and this one) ship `result.json` instead. Recorded
  here rather than claimed green.
- Wave 3's burn-down of `remaining_amount` has no target-side implementation yet, so no
  evidence covers it.
