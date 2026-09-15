# Unit p1-invoice-lines (U-07 INVOICE_LINES, modern) — Lakebase `billing.invoice_lines`

Wave 3, batch w3-b. Source `OW_BILLING.INVOICE_LINES` (2 rows, read-only), target `ow_tp` /
schema `billing` on Lakebase branch `mig-p1-w2`. DDL:
`databricks/migration/lakebase/w3b_invoice_lines.sql`. Load:
`databricks/migration/transport/oracle_to_lakebase_load.py` with
`.migration/units/p1-invoice-lines/mapping_spec.json`.

Modern generation (D9-01). The legacy `INVOICE_LINE` table — singular, 150k rows, 37
orphans — is a different object and went to Delta in wave 1.

## Column mapping

| Oracle | Lakebase | Why |
|---|---|---|
| `id VARCHAR2(36) NOT NULL` | `id varchar(36) NOT NULL` | key, empty string is NULL |
| `invoice_id VARCHAR2(36) NOT NULL` | `invoice_id varchar(36) NOT NULL` | parent `billing.invoices` (unit p1-invoices) |
| `line_no NUMBER(6) NOT NULL` | `line_no integer NOT NULL` | scale 0, range fits |
| `line_type VARCHAR2(10) NOT NULL` | `line_type varchar(10) NOT NULL` | free text: Oracle has no check constraint |
| `description VARCHAR2(400) NOT NULL` | `description varchar(400) NOT NULL` | length preserved |
| `amount NUMBER(12,2) NOT NULL` | `amount numeric(12,2) NOT NULL` | money is exact decimal, never float |

## Constraints and indexes

All three Oracle constraints are recreated under their Oracle names: `pk_invoice_lines`,
`uq_invoice_lines` (`invoice_id, line_no`) and `fk_il_invoice`
(`invoice_id` → `billing.invoices(id)` `ON DELETE CASCADE`). The source has no orphan line
in this table, so reproducing the FK does not collide with D8-01. The cascade is kept
because it is source behaviour, not a convenience.

Oracle's only indexes here are the implicit unique indexes behind the primary key and the
unique constraint; the Postgres constraints provide the same, so nothing extra is created.

## Dependency

`billing.invoices` comes from unit `p1-invoices` (same batch, separate PR). This DDL does
not create it — substituting another unit's DDL is forbidden — so on a fresh branch apply
`w3b_invoices.sql` first. On the wave branch the table already exists.

## Load and recon

- One live Oracle read for the load; development ran against the fixture
  (`make oracle-billing-up`, `make oracle-billing-seed NS=w3b`).
- Recon evidence: `.migration/recon/p1-invoice-lines/` (fixture run under `fixture/`).
  Every verdict on this run is graded DEGRADED, `official_verdict=false`,
  `reason=d10_01_denied`, and is not an official harness verdict.

## What this unit does not write

Only `billing.invoice_lines`. Not `billing.invoices`, not `billing.credit_notes`, and no
audit or log table. The runtime rebuild of lines (`DELETE` + re-insert) belongs to
`p1-pkg-invoicing`.
