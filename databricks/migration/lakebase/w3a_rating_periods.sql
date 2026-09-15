-- U-04 RATING_PERIODS -> Lakebase billing.rating_periods (unit p1-rating-periods, wave 3 batch a).
--
-- Oracle source: OW_BILLING.RATING_PERIODS (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- Oracle DATE carries a time part, so PERIOD_START/PERIOD_END become timestamp(0), not date:
-- the source rows are midnight today, but truncating the type would silently drop a time the
-- source is free to store. No zone is recorded on the source; UTC is assumed and declared
-- (plan decision P1-D3).
--
-- Ids are f_md5_uuid outputs (wave 0), so they stay varchar(36) text rather than becoming a
-- uuid column: the parity proof compares the text form byte for byte.
--
-- Both Oracle constraints keep their original names - primary key on ID and the unique key on
-- (TENANT_ID, PERIOD_START) that makes sp_finalize_rating's insert-then-catch upsert work.
-- The foreign key to billing.tenants keeps its Oracle name too; tenants is merged by wave 1
-- and this statement only reads it, it does not alter it.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.rating_periods (
    id           varchar(36)  NOT NULL,
    tenant_id    varchar(36)  NOT NULL,
    period_start timestamp(0) NOT NULL,
    period_end   timestamp(0) NOT NULL,
    CONSTRAINT pk_rating_periods PRIMARY KEY (id),
    CONSTRAINT uq_rating_periods UNIQUE (tenant_id, period_start),
    CONSTRAINT fk_rp_tenant FOREIGN KEY (tenant_id) REFERENCES billing.tenants (id)
);

COMMENT ON TABLE billing.rating_periods IS
    'Migration unit p1-rating-periods (U-04) from Oracle OW_BILLING.RATING_PERIODS.';
COMMENT ON COLUMN billing.rating_periods.id IS
    'Deterministic MD5 uuid from billing.f_md5_uuid(tenant_id || period_start), wave 0 parity proof.';
