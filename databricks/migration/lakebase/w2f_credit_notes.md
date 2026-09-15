# Unit p1-credit-notes (U-08 CREDIT_NOTES) - Lakebase `billing.credit_notes`

Wave 2, batch w2-f. Source `OW_BILLING.CREDIT_NOTES` (5 rows, read-only), target
`ow_tp` / schema `billing` on Lakebase branch `mig-p1-w2`. DDL:
`databricks/migration/lakebase/w2f_credit_notes.sql`. Load:
`databricks/migration/transport/oracle_to_lakebase_load.py` with
`.migration/units/p1-credit-notes/mapping_spec.json`.

## Column mapping

| Oracle | Lakebase | Why |
|---|---|---|
| `id VARCHAR2(36) NOT NULL` | `id varchar(36) NOT NULL` | key, empty string is NULL |
| `tenant_id VARCHAR2(36) NOT NULL` | `tenant_id varchar(36) NOT NULL` | parent `billing.tenants` (wave 1) |
| `issued_on DATE NOT NULL` | `issued_on timestamp(0) NOT NULL` | Oracle DATE keeps its time part (P1-D3, UTC assumed) |
| `amount NUMBER(12,2) NOT NULL` | `amount numeric(12,2) NOT NULL` | money is exact decimal, never float |
| `remaining_amount NUMBER(12,2) NOT NULL` | `remaining_amount numeric(12,2) NOT NULL` | same |

Constraints carried over under their Oracle names: `pk_credit_notes` (PK on `id`) and
`fk_cn_tenant` (`tenant_id` -> `billing.tenants(id)`). The source enforces `fk_cn_tenant`
and holds no orphan credit note, so recreating it does not collide with D8-01 (orphans are
reproduced, not cleaned). Nothing else is added.

Indexes: Oracle has one index on this table, the implicit unique index behind
`PK_CREDIT_NOTES`. The Postgres primary key provides the same index, so the DDL creates no
extra index and none is invented for the burn-down scan.

## Ordering guarantee (contract for wave 3, w3-b)

`pkg_invoicing` burns credit down oldest-first and wave 3 must keep doing exactly that:

```sql
SELECT id, remaining_amount FROM billing.credit_notes
 WHERE tenant_id = :tenant_id AND remaining_amount > 0
 ORDER BY issued_on, id
```

- The order is `(issued_on ASC, id ASC)`, ties on `issued_on` broken by `id`. The fixture
  has such a tie (`...0001` and `...0002`, both 2026-02-01), so the tiebreak is observable,
  not theoretical.
- `id` ordering is byte order. Oracle sorts `VARCHAR2` with `NLS_SORT=BINARY`, and the
  Lakebase database is `C.UTF-8`, so plain `ORDER BY ... , id` already matches Oracle. If
  this table is ever read from a database or column with a non-binary collation, the
  consumer must write `id COLLATE "C"` to keep the same order.
- `issued_on` is `timestamp(0)`, so the second-level values Oracle stores compare as Oracle
  compares them; a `date` column would have collapsed same-day rows and changed the order.
- The wave-3 burn-down (`UPDATE ... SET remaining_amount = GREATEST(remaining_amount - v_credit, 0)`
  with the running counter `pkg_invoicing` keeps) is **not** implemented in this unit, and
  this unit writes no other table - in particular not `billing.invoices` or
  `billing.invoice_lines`.

## Load and recon

- One live Oracle read for the unit; development ran against the fixture
  (`make oracle-billing-up`).
- Loader deletes source-dropped keys before upserting, sets
  `oracledb.defaults.fetch_decimals = True` (money stays exact), and connects to the direct
  Lakebase endpoint host.
- Recon evidence: `.migration/recon/p1-credit-notes/` (fixture run under `fixture/`).
  Every verdict on this run is graded DEGRADED, `official_verdict=false`,
  `reason=d10_01_denied`, and is not an official harness verdict.
