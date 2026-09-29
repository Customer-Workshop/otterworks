PostgreSQL DDL for schemas mig/stg/arch (binding: ../../CONTRACTS.md §6 and the Providers section);
idempotent, applied in file-name order by `ldm init` when `target.provider: postgresql` (the default).

The schemas are created inside the tenant's *existing* database (`otterworks_<tenant>` on the shared
RDS instance) - no database is created here and nothing outside these three schemas is touched.
Key/range text columns use `COLLATE "C"` so range ordering and hash inputs are byte-ordered like the
Db2 source; Db2 `TIMESTAMP(12)` is `TIMESTAMP(6)` + `<COL>_NANOS_TAIL INTEGER` (digits 7-12, lossless).
`100_grants.sql` grants the application role read access to `mig.*` views and `arch.*` for the
report-service / audit-service archive read path. Teardown drops the whole tenant database
(`scripts/teardown-tenant.sh`), which removes these schemas with it.
