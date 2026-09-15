# Unit p1-usage-events-oltp (U-28 USAGE_EVENTS) — Lakebase `billing.usage_events`

Wave 4, batch w4-c. Source `OW_BILLING.USAGE_EVENTS` (read-only), target `ow_tp` / schema
`billing` on Lakebase branch `mig-p1-w2`. DDL:
`databricks/migration/lakebase/w4c_usage_events.sql`. Load:
`databricks/migration/transport/oracle_to_lakebase_load.py` with
`.migration/units/p1-usage-events-oltp/mapping_spec.json`.

## Why this table exists twice

The same source table already landed in Delta as `ow_tp.silver.usage_events` (U-18, wave 1).
That copy stays and is the analytical one. This is the operational copy the converted
`pkg_rating` reads row-at-a-time in `compute_rating` and `fn_usage_summary` (decision D-011).
Two targets of one source, with disjoint write targets: each reconciles against Oracle, and
neither is ever reconciled against the other. Keeping the two copies in step after cutover
needs a named owner — that is recorded for STOP E, not solved here.

## Column mapping

| Oracle | Lakebase | Why |
|---|---|---|
| `id VARCHAR2(36) NOT NULL` | `id varchar(36) NOT NULL` | key, empty string is NULL |
| `tenant_id VARCHAR2(36) NOT NULL` | `tenant_id varchar(36) NOT NULL` | parent `billing.tenants` (wave 1) |
| `occurred_at TIMESTAMP(6) NOT NULL` | `occurred_at timestamp(6) NOT NULL` | Oracle TIMESTAMP is zoneless → `timestamp`, never `timestamptz` (D-010); UTC assumed and declared (P1-D3) |
| `units NUMBER(10) NOT NULL` | `units bigint NOT NULL` | integral counter, exact; not money, not float |
| `kind_cd NUMBER(4) NOT NULL` | `kind_cd smallint NOT NULL` | `USAGE_KIND` magic number, kept as-is |

Constraints carried over under their Oracle names: `pk_usage_events` (PK on `id`) and
`fk_usage_tenant` (`tenant_id` → `billing.tenants(id)`). The source enforces the FK and holds
no orphan usage event, so recreating it does not collide with D8-01 (orphans are reproduced,
not cleaned).

Indexes: Oracle has one index on this table, the implicit unique index behind
`PK_USAGE_EVENTS`; the Postgres primary key provides the same index. Nothing extra is added.

## Declared coverage gap

`TRG_USAGE_EVENTS_CHECK` (BEFORE INSERT: `units > 0`, `kind_cd` must exist in
`CODES('USAGE_KIND')`) is **not** reproduced. This unit creates the table and loads rows
Oracle already accepted, so no row it writes could have tripped the trigger; an insert-time
rule belongs with the converted write path, not with a data unit. Both conditions were
checked as data on the source (0 rows with `units <= 0`, 0 rows with an unknown kind) and the
unit does not claim the rule as migrated. Any later unit that makes the application write
this table has to carry the rule.

## Load and recon

- One live Oracle read for the unit; development ran against the fixture
  (`make oracle-billing-up`).
- Loader upserts on `id` and deletes keys the source no longer has, so a rerun converges;
  `oracledb.defaults.fetch_decimals = True` keeps every NUMBER exact.
- Recon evidence: `.migration/recon/p1-usage-events-oltp/` (fixture run under `fixture/`).
  Every verdict on this run is graded DEGRADED, `official_verdict=false`,
  `reason=d10_01_denied`, and is not an official harness verdict.
