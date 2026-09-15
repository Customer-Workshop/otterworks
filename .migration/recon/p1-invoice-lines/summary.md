# p1-invoice-lines (U-07, wave 3 / batch w3-b) — recon evidence

**Verdict: PASS, graded DEGRADED (`official_verdict=false`, `reason=d10_01_denied`).**
This is not an official harness verdict. D10-01 was denied, so Oracle is read over JDBC with
a repo-local source adapter (`databricks/migration/recon/oracle_jdbc_adapter.py`); every
tier, tolerance and canonicalization rule is still the harness's own. See `DEGRADED.md`,
`result.json`, `recon.summary.md`.

Merge-evidence run: `--mode transactional --depth full --seed 0`, against the live source.
The fixture run (`fixture/`) came first and is development evidence only, never a merge
verdict. Two full runs used of the three-run cap.

## What was compared

`OW_BILLING.INVOICE_LINES` (2 rows, the modern generation — D9-01, not the legacy
`INVOICE_LINE` table with 150k rows and 37 orphans that went to Delta in wave 1) against
`billing.invoice_lines` on Lakebase branch `mig-p1-w2`, through
`.migration/units/p1-invoice-lines/mapping_spec.json`.

| tier | result | scope |
|---|---|---|
| 0 consistency_window | PASS | source snapshot vs target repeatable_read, held |
| 1 counts_through_mapping | PASS | 2 = 2 |
| 2 per_field_aggregates | PASS | 6 checks |
| 3 keyed_diffs | PASS | 2 keys, full diff, zero mismatches |
| 5 pk_set_diff | PASS | 2 keys |
| 6 cdc_lag_ordering | PASS (0 checks) | the mapping declares no watermark for this table |
| 7 schema_parity | PASS (0 checks) | source metadata unreadable over JDBC — see below |

Target values are read back from Lakebase by the harness, never from the loader's output.

## Conversion decisions this evidence covers

- `amount` is `NUMBER(12,2)` → `numeric(12,2)`, compared exactly; the loader sets
  `oracledb.defaults.fetch_decimals = True`, so money never becomes a float.
- `line_no` is `NUMBER(6)` → `integer`: the Oracle range fits and the scale is 0, so no
  value can be lost.
- `line_type` stays free text (`varchar(10)`). Oracle declares no check constraint, so the
  values `pkg_invoicing` writes (`BASE`, `OVERAGE`, `CREDIT`) are convention, not a domain,
  and no domain was invented on the target.
- All three Oracle constraints are recreated under their Oracle names: `pk_invoice_lines`,
  `uq_invoice_lines` (`invoice_id, line_no`) and `fk_il_invoice`
  (`invoice_id` → `billing.invoices(id)`, `ON DELETE CASCADE`). The source has no orphan
  line in this modern table (checked: 0), so reproducing the FK does not collide with D8-01.
  The cascade matters behaviourally: `pkg_invoicing` rebuilds lines by deleting them, and
  the wave-1 legacy table's 37 orphans belong to a different object entirely.
- The only Oracle indexes are the implicit unique indexes behind `PK_INVOICE_LINES` and
  `UQ_INVOICE_LINES`; the Postgres constraints provide the same, so none was added.

## Dependency

`billing.invoices` is created by unit `p1-invoices` in this same batch (its own PR). This
unit does not create it: substituting another unit's DDL is what the wave forbids. The table
already exists on the shared branch, so the foreign key was created for real and this
evidence covers it.

Ledger decision D-010 (Oracle `TIMESTAMP` → Postgres `timestamp(6)`, never `timestamptz`)
does not change this table: `INVOICE_LINES` has no datetime column. This evidence is the
re-run against the corrected mapping specs, so the run matches the current manifest.

## Idempotency

Proven by rerun, not inferred. The loader ran against the fixture, then live, then against
the fixture again, reporting `source_rows=2 target_rows=2 deleted=0` every time. The target
was digested from Lakebase before and after the final rerun and did not move:

    rows=2 sha256=696379c5b010f5f0efec86d405a8ada27bbe629444cff986f0c64574b91f42d5

It deletes target keys the source no longer has before upserting, so a rerun converges
rather than accumulating.

## NOT DATA-PROVEN / unverified paths

- Tiers 5–7 source-side metadata (constraints, indexes, identity): the JDBC adapter reads no
  catalog metadata, so these are reported unverified rather than guessed. That is also why
  `merge_eligible` is `false` — structural on this route, not a failure of this unit.
- Tier 6 ran 0 checks: the mapping declares no watermark column for this table, so CDC lag
  and ordering are not covered by this evidence.
- `source_principal_read_only` is `unverified` in the capability preflight: the doctor has no
  privilege query for the Oracle family. This unit used the read-only credential
  (`ow-tp/oracle/ow_billing_ro`) and issued no DDL or DML against Oracle, but the grants
  themselves were not machine-checked.
- `lakebase_branch_create` is `fail` in the same preflight because the shared parent branch
  `mig-p1-w2` carries an expiry. The branch exists and was used as it is; it was not
  created, reset or re-branched.
- Rows written at runtime by the converted `pkg_invoicing` are not covered here: this
  evidence is a snapshot of the migrated source rows, taken before that unit's procedure
  ran.
