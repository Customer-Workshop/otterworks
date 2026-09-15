# p1-usage-events-oltp (U-28, wave 4 / batch w4-c) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter (`databricks/migration/recon/oracle_jdbc_adapter.py`); every
tier, tolerance and canonicalization rule is still the harness's own. See `DEGRADED.md`,
`result.json`, `recon.summary.md`.

Merge-evidence run: `--mode transactional --depth full --seed 0`. A fixture run (`fixture/`)
came first and is development evidence only, never a merge verdict. Two full runs used of
the three-run cap.

## What was compared

`OW_BILLING.USAGE_EVENTS` (814 rows) against `billing.usage_events` on Lakebase branch
`mig-p1-w2`, through `.migration/units/p1-usage-events-oltp/mapping_spec.json`.

| tier | result | scope |
|---|---|---|
| 0 consistency_window | PASS | source snapshot vs target repeatable_read, held |
| 1 counts_through_mapping | PASS | 814 = 814 |
| 2 per_field_aggregates | PASS | 5 columns |
| 3 keyed_diffs | PASS | 814 keys, full diff, zero mismatches |
| 5 pk_set_diff | PASS | 814 keys |
| 6 cdc_lag_ordering | PASS | `occurred_at` watermark, 1 check |
| 7 schema_parity | PASS (0 checks) | source metadata unreadable over JDBC — see below |

Target values are read back from Lakebase by the harness, never from the loader's output.
This unit was reconciled against Oracle, not against the Delta copy `ow_tp.silver.usage_events`
(U-18): two targets of one source, never one target of another. The Delta copy was not read
or written here.

## Conversion decisions this evidence covers

- `occurred_at` is Oracle `TIMESTAMP(6)`, zoneless → `timestamp(6)`, never `timestamptz`
  (D-010; UTC assumed and declared under P1-D3).
- `units` `NUMBER(10,0)` → `bigint` and `kind_cd` `NUMBER(4,0)` → `smallint`, both exact
  integers. `kind_cd` stays a magic number; no lookup or enum was introduced.
- `id` and `tenant_id` `VARCHAR2(36)` → `varchar(36)`; Oracle's empty-string-is-NULL
  behaviour is carried by the mapping rule, not cleaned.
- Constraints recreated under their Oracle names: `pk_usage_events` and `fk_usage_tenant`
  (`tenant_id` → `billing.tenants(id)`, merged in wave 1). Source holds no orphan usage
  event, so D8-01 is not in tension here. No index or constraint Oracle does not have was
  added.
- Write scope: only `billing.usage_events`. `pkg_rating`, the rating tables, `billing.invoices`
  and the Delta copy were untouched.

## Idempotency

Proven by rerun, not inferred. The loader ran again against the same source after the
merge-evidence recon, and the target digest (read back from Lakebase with
`target_digest.py`) was unchanged before and after:

    rows=814 sha256=2eb32e323834c9872e0ecda586e6ff3e926e135954f7ff7e6ae9cd1064940dd0

The loader deletes target keys the source no longer has before upserting, so a rerun
converges rather than accumulating (`source_rows=814 target_rows=814 deleted=0` on both
runs).

## NOT DATA-PROVEN / unverified paths

- Tiers 5–7 source-side metadata (constraints, indexes, identity): the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. That is also why
  `merge_eligible` is `false` — structural on this route, not a failure of this unit.
- Oracle trigger `TRG_USAGE_EVENTS_CHECK` (positive `units`, known `kind_cd`) has no target
  equivalent in this unit. It is a write-path rule; this unit loads rows Oracle already
  accepted, and no converted writer exists yet. Declared coverage gap, carried to w4-d.
- The idempotency rerun used a second read of the live source rather than the fixture: the
  fixture holds a 10-row subset of the same keys, so reloading from it would have deleted
  804 live rows. Recorded rather than worked around; see the report to the orchestrator.
- `source_principal_read_only` is `unverified` in the capability preflight: the doctor has no
  privilege query for the Oracle family. The unit used the read-only credential
  (`ow-tp/oracle/ow_billing_ro`) and issued no DDL or DML against Oracle, but the grants
  themselves were not machine-checked.
- No `*.recon.json` (`"kind": "recon-report"`) is emitted. `emit_recon_report.py` recounts
  declared anomaly classes over `ow_tp.silver.*` on the SQL warehouse and reads two
  Delta target-state digests, so it covers the Delta track; the Lakebase units
  (`p1-tenants`, `p1-plans`, `p1-codes`, `p1-credit-notes`, and this one) ship `result.json`
  instead. Recorded here rather than claimed green.
- The consumers of this table (`pkg_rating.compute_rating`, `fn_usage_summary`) are wave 4's
  w4-d; nothing here verifies them.
