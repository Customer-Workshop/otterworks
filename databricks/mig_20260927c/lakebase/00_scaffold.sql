-- Run 20260927c, unit lakebase_scaffold (wave 0).
-- Lakebase project ow-tp-billing, database ow_tp, branch mig-20260927c-w0 only.
-- Types are exactly .migration/units/lakebase_scaffold/mapping_spec.json
-- (map-20260927c-lakebase_scaffold-v1); keys, uniques, foreign keys and NOT NULLs are the
-- Oracle dictionary for OW_BILLING.CODES/PLANS/TENANTS/USAGE_EVENTS.
-- Idempotent: every statement is IF NOT EXISTS, so a rerun makes no changes. Nothing is
-- dropped here; table replacement is load_reference.py's job (TRUNCATE + COPY).

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

-- No triggers: the live OW_BILLING dictionary declares none on these four tables (the local
-- fixture's TRG_USAGE_EVENTS_CHECK is fixture-only and is not reproduced here).

-- Lakebase auto-grants every new table to the platform role databricks_superuser (and, through
-- membership, to workspace admins). OW_BILLING grants nothing beyond the owner, so the target
-- carries only the owner (the migration service principal) and the platform reader roles.
REVOKE ALL ON billing.codes, billing.plans, billing.tenants, billing.usage_events FROM databricks_superuser;
