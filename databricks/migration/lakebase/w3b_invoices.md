# Unit p1-invoices (U-06 INVOICES, modern) — Lakebase `billing.invoices`

Wave 3, batch w3-b. Source `OW_BILLING.INVOICES` (3 rows, read-only), target `ow_tp` /
schema `billing` on Lakebase branch `mig-p1-w2`. DDL:
`databricks/migration/lakebase/w3b_invoices.sql`. Load:
`databricks/migration/transport/oracle_to_lakebase_load.py` with
`.migration/units/p1-invoices/mapping_spec.json`.

This is the modern invoice generation (D9-01). It is not the legacy
`INVOICE_HEADER`/`INVOICE_LINE` pair migrated to Delta in wave 1; both generations exist in
the source and land in different targets.

## Column mapping

| Oracle | Lakebase | Why |
|---|---|---|
| `id VARCHAR2(36) NOT NULL` | `id varchar(36) NOT NULL` | key, empty string is NULL |
| `tenant_id VARCHAR2(36) NOT NULL` | `tenant_id varchar(36) NOT NULL` | parent `billing.tenants` (wave 1) |
| `period_id VARCHAR2(36) NOT NULL` | `period_id varchar(36) NOT NULL` | parent `rating_periods` is not on this branch — see below |
| `issued_at TIMESTAMP NOT NULL` | `issued_at timestamp(6) NOT NULL` | Oracle TIMESTAMP is zoneless (D-010); UTC assumed (P1-D3) |
| `subtotal NUMBER(12,2) NOT NULL` | `subtotal numeric(12,2) NOT NULL` | money is exact decimal, never float |
| `tax NUMBER(12,2) NOT NULL` | `tax numeric(12,2) NOT NULL` | same |
| `total NUMBER(12,2) NOT NULL` | `total numeric(12,2) NOT NULL` | same |
| `status_cd NUMBER(4) NOT NULL` | `status_cd smallint NOT NULL` | magic status code stays a number |

`issued_at` is `timestamp(6)` under ledger decision D-010: a `timestamptz` column reads back
tz-aware and fails Tier 3 against Oracle's naive value on every row, which is how this unit's
first run failed. Wave 0 had made the same correction for `billing.billing_audit_log`.
The unit mapping spec and `databricks/migration/tools/gen_mapping_specs.py` now emit
`timestamp(p)`.

## Constraints and indexes

`pk_invoices` (PK on `id`) and `fk_inv_tenant` (`tenant_id` → `billing.tenants(id)`, wave 1)
are recreated under their Oracle names. The source holds no orphan invoice, so reproducing
the tenant FK does not collide with D8-01 (orphans are reproduced, not cleaned).

`fk_inv_period` (`period_id` → `RATING_PERIODS`) is **not** recreated. `rating_periods`
belongs to the rating unit running concurrently in this wave and is not on the branch;
creating another unit's table to hang a constraint on would be a write outside this batch's
declared targets. The column and its values are unchanged, and the constraint is a wave-gate
item once that unit merges.

Oracle has one index on the table, the implicit unique index behind `PK_INVOICES`; the
Postgres primary key provides the same one, so no extra index is created.

## Load and recon

- One live Oracle read for the load; development ran against the fixture
  (`make oracle-billing-up`, `make oracle-billing-seed NS=w3b`).
- The loader deletes source-dropped keys before upserting and sets
  `oracledb.defaults.fetch_decimals = True`, so money stays exact.
- Recon evidence: `.migration/recon/p1-invoices/` (fixture run under `fixture/`). Every
  verdict on this run is graded DEGRADED, `official_verdict=false`,
  `reason=d10_01_denied`, and is not an official harness verdict.

## What this unit does not write

Only `billing.invoices`. Not `billing.invoice_lines` (unit p1-invoice-lines), not
`billing.credit_notes` (wave 2 owns the DDL; the burn-down DML belongs to
p1-pkg-invoicing), and no audit or log table.
