-- U-28 USAGE_EVENTS -> Lakebase billing.usage_events (unit p1-usage-events-oltp, wave 4 batch c).
--
-- Oracle source: OW_BILLING.USAGE_EVENTS (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- This is the OPERATIONAL copy pkg_rating reads (D-011). The analytical copy of the same
-- source table is ow_tp.silver.usage_events (U-18, wave 1); the two are separate targets of
-- one source and each reconciles against Oracle, never against the other.
-- Idempotent: every statement is CREATE ... IF NOT EXISTS (P1-D6).
--
-- Types follow the unit mapping spec and the wave-1 dialect rules:
--   VARCHAR2(36) -> varchar(36); NUMBER(10) -> bigint and NUMBER(4) -> smallint (integral
--   counters, never float); Oracle TIMESTAMP(6) is zoneless, so occurred_at is
--   timestamp(6) and never timestamptz (D-010, and P1-D3 for the UTC assumption).
--
-- Constraints: both Oracle constraints are recreated under their Oracle names.
-- fk_usage_tenant is enforced in the source and the source carries no orphan usage event
-- (checked on the fixture and on the live read), so reproducing it does not conflict with
-- D8-01; the parent billing.tenants merged in wave 1. No constraint Oracle does not have is
-- added.
--
-- Indexes: the source table has exactly one index, the implicit unique index behind
-- PK_USAGE_EVENTS. The Postgres primary key provides the same index, so no CREATE INDEX is
-- issued and no covering index is invented for the rating scan - Oracle does not have one.
--
-- NOT carried here, deliberately: TRG_USAGE_EVENTS_CHECK, the BEFORE INSERT trigger that
-- rejects units <= 0 (ORA-20001) and an unknown USAGE_KIND (ORA-20002). This unit is the
-- table and its load; it writes no rows the trigger would have rejected (the load copies
-- rows Oracle already accepted) and reproducing an insert-time rule belongs with the write
-- path, not with a data unit. It is listed as a coverage gap in w4c_usage_events.md, not
-- claimed as migrated.
--
-- The billing schema and billing.tenants are wave-1 objects and must already exist; this
-- unit creates neither, so a missing prerequisite fails here instead of being papered over.

CREATE TABLE IF NOT EXISTS billing.usage_events (
    id          varchar(36)  NOT NULL,
    tenant_id   varchar(36)  NOT NULL,
    occurred_at timestamp(6) NOT NULL,
    units       bigint       NOT NULL,
    kind_cd     smallint     NOT NULL,
    CONSTRAINT pk_usage_events PRIMARY KEY (id),
    CONSTRAINT fk_usage_tenant FOREIGN KEY (tenant_id) REFERENCES billing.tenants (id)
);

COMMENT ON TABLE billing.usage_events IS
    'Migration unit p1-usage-events-oltp (U-28) from Oracle OW_BILLING.USAGE_EVENTS. '
    'Operational copy read by the converted pkg_rating (D-011); the analytical copy is '
    'ow_tp.silver.usage_events (U-18). Loaded by the migration, not by the application.';
COMMENT ON COLUMN billing.usage_events.occurred_at IS
    'Oracle TIMESTAMP(6), zoneless: timestamp(6) and never timestamptz (D-010). UTC is '
    'assumed and declared (P1-D3).';
COMMENT ON COLUMN billing.usage_events.kind_cd IS
    'USAGE_KIND status code, kept as the legacy magic number (values live in billing.codes); '
    'the source-side insert check TRG_USAGE_EVENTS_CHECK is not reproduced by this unit.';
