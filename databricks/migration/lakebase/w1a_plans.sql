-- U-02 PLANS -> Lakebase billing.plans (unit p1-plans, wave 1 batch a).
--
-- Oracle source: OW_BILLING.PLANS (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- Money keeps its exact decimal type: NUMBER(12,2) -> numeric(12,2) and NUMBER(12,6) ->
-- numeric(12,6). Never float - recon compares these two columns for exact equality, and a
-- binary float would lose the last cent on a value like 199.99.
-- NUMBER(10) counts become bigint (Postgres has no 10-digit integer type; int would overflow
-- at 2,147,483,647, which is inside NUMBER(10)'s range).
-- TIER_CD stays the magic number the application writes (billing.codes('PLAN_TIER')).
--
-- Both Oracle constraints keep their original names: primary key on ID, unique key on CODE.
-- Each is indexed implicitly by Postgres, as it was by Oracle.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.plans (
    id             varchar(36)   NOT NULL,
    code           varchar(50)   NOT NULL,
    tier_cd        smallint      NOT NULL,
    monthly_fee    numeric(12,2) NOT NULL,
    included_units bigint        NOT NULL,
    overage_rate   numeric(12,6) NOT NULL,
    active_yn      char(1)       DEFAULT 'Y' NOT NULL,
    CONSTRAINT pk_plans PRIMARY KEY (id),
    CONSTRAINT uq_plans_code UNIQUE (code)
);

COMMENT ON TABLE billing.plans IS
    'Migration unit p1-plans (U-02) from Oracle OW_BILLING.PLANS.';
COMMENT ON COLUMN billing.plans.tier_cd IS
    'Magic tier code, billing.codes(''PLAN_TIER''): 1 starter, 2 growth, 3 scale.';
