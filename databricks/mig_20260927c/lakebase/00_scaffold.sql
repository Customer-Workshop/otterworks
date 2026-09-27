-- Run 20260927c, unit lakebase_scaffold (wave 0).
-- Lakebase project ow-tp-billing, database ow_tp, branch mig-20260927c-w0 only.
-- Types are exactly .migration/units/lakebase_scaffold/mapping_spec.json (map-20260927c-lakebase_scaffold-v1);
-- keys, uniques, foreign keys and NOT NULLs are the Oracle dictionary
-- .migration/inventory/oracle_dictionary_20260927c.json (OW_BILLING.CODES/PLANS/TENANTS/USAGE_EVENTS).
-- Idempotent by drop/recreate: the four unit-owned tables are dropped (FK order) and the schema is
-- dropped only when nothing else lives in it, so a rerun lands exactly the declared shape and
-- never touches a table another unit owns.

DROP TABLE IF EXISTS billing.usage_events;
DROP TABLE IF EXISTS billing.tenants;
DROP TABLE IF EXISTS billing.plans;
DROP TABLE IF EXISTS billing.codes;
DO $$
BEGIN
    DROP SCHEMA IF EXISTS billing RESTRICT;
EXCEPTION WHEN dependent_objects_still_exist THEN
    RAISE NOTICE 'schema billing kept: other objects live in it';
END $$;

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.codes (
    code_type varchar(30) NOT NULL,
    code_val  bigint      NOT NULL,
    code_desc varchar(80) NOT NULL,
    CONSTRAINT pk_codes PRIMARY KEY (code_type, code_val)
);

CREATE TABLE IF NOT EXISTS billing.plans (
    id             varchar(36)   NOT NULL,
    code           varchar(50)   NOT NULL,
    tier_cd        bigint        NOT NULL,
    monthly_fee    numeric(12,2) NOT NULL,
    included_units bigint        NOT NULL,
    overage_rate   numeric(12,6) NOT NULL,
    active_yn      char(1)       NOT NULL,
    CONSTRAINT pk_plans PRIMARY KEY (id),
    CONSTRAINT uq_plans_code UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS billing.tenants (
    id            varchar(36)  NOT NULL,
    name          varchar(200) NOT NULL,
    tax_exempt_yn char(1)      NOT NULL,
    status_cd     bigint       NOT NULL,
    CONSTRAINT pk_tenants PRIMARY KEY (id),
    CONSTRAINT uq_tenants_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS billing.usage_events (
    id          varchar(36)  NOT NULL,
    tenant_id   varchar(36)  NOT NULL,
    occurred_at timestamp(6) NOT NULL,
    units       bigint       NOT NULL,
    kind_cd     bigint       NOT NULL,
    CONSTRAINT pk_usage_events PRIMARY KEY (id),
    CONSTRAINT fk_usage_tenant FOREIGN KEY (tenant_id) REFERENCES billing.tenants (id)
);

-- No triggers: the live OW_BILLING dictionary declares none on these four tables (the local fixture's
-- TRG_USAGE_EVENTS_CHECK is fixture-only and is not reproduced here).
