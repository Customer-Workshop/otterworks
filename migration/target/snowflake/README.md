Snowflake DDL for the archive store of a split target (`target.provider: snowflake`, binding:
`../../CONTRACTS.md` §6/§8 and `SNOWFLAKE-PORT-SPEC.md` §3). Idempotent, applied in file-name order by
`ldm init` inside the tenant database `OTTERWORKS_LDM_<TOKEN>` and tracked in `MIG.SCHEMA_VERSION`.

Split: the tenant's PostgreSQL database keeps the transactional control plane (`mig.runs`, `run_ledger`,
`key_ranges`, `rejects`, `validation`, `class_totals`, `purge_audit`, `stage_log` - the
`../postgresql` DDL, applied by the same `ldm init`). Snowflake holds `STG.*` (this run's converted rows,
loaded from Parquet via the internal stage `STG.LDM_STAGE` with `COPY INTO`), `ARCH.*` (the served
archive) and `MIG.*` as a mirror of the verdicts written at promotion / run close, so promotion and the
`MIG.V_*` reporting views are set-based inside Snowflake.

Snowflake `CHAR(n)` is `VARCHAR(n)`: fixed-width values keep their padding as loaded and the hash
expression (`ldm/hashing.py::snowflake_hash_expression`) re-pads keys with `RPAD`. Db2 `TIMESTAMP(12)` is
`TIMESTAMP_NTZ(6)` + `<COL>_NANOS_TAIL INTEGER`. Uniqueness of `(NAMESPACE, SOURCE_KEY)` in `STG.*` is not
enforced by Snowflake; the driver removes cross-run duplicates after each `COPY` and reports them as
`DUPLICATE_SOURCE_KEY` rejects (MIG-06), exactly like the PostgreSQL unique index does.

Account-level objects (role `LDM_ADMIN`, warehouse, service user, per-tenant database + job/reader roles)
are created by `scripts/lib/snowflake-bootstrap.sql` / `scripts/deploy-demo.sh`, not here. Teardown drops
the tenant database (`scripts/teardown-tenant.sh`).
