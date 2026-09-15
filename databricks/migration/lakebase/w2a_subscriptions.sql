-- U-03 SUBSCRIPTIONS -> Lakebase billing.subscriptions (unit p1-subscriptions, wave 2 batch a).
--
-- Oracle source: OW_BILLING.SUBSCRIPTIONS (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- Idempotent: every statement is CREATE ... IF NOT EXISTS or CREATE OR REPLACE (P1-D6).
--
-- Types follow the unit mapping spec and the wave-1 dialect rules:
--   VARCHAR2(36)/VARCHAR2(50) -> varchar(n); NUMBER(4) -> smallint (status codes stay the
--   magic numbers the application writes, billing.codes('SUB_STATUS'): 10 active,
--   20 suspended, 30 cancelled); Oracle DATE carries a time part, so the three date columns
--   are timestamp(0) and never date (P1-D3, UTC assumed and declared).
--
-- Constraints: the primary key keeps its Oracle name. The two Oracle foreign keys
-- (fk_sub_tenant, fk_sub_plan) are deliberately NOT recreated. D8-01 requires orphan rows to
-- be reproduced rather than cleaned, and a foreign key here would reject exactly those rows
-- on load; billing.tenants and billing.plans are also loaded by other units, so a constraint
-- would couple this unit's load order to theirs. The referential relationship is documented,
-- not enforced.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.subscriptions (
    id           varchar(36)  NOT NULL,
    tenant_id    varchar(36)  NOT NULL,
    plan_id      varchar(36)  NOT NULL,
    starts_on    timestamp(0) NOT NULL,
    ends_on      timestamp(0),
    status_cd    smallint     NOT NULL,
    suspended_on timestamp(0),
    CONSTRAINT pk_subscriptions PRIMARY KEY (id)
);

COMMENT ON TABLE billing.subscriptions IS
    'Migration unit p1-subscriptions (U-03) from Oracle OW_BILLING.SUBSCRIPTIONS.';
COMMENT ON COLUMN billing.subscriptions.status_cd IS
    'Magic status code, billing.codes(''SUB_STATUS''): 10 active, 20 suspended, 30 cancelled.';
COMMENT ON COLUMN billing.subscriptions.tenant_id IS
    'References billing.tenants(id) in the source; not enforced here, see D8-01 orphans.';
COMMENT ON COLUMN billing.subscriptions.plan_id IS
    'References billing.plans(id) in the source; not enforced here, see D8-01 orphans.';

-- TRG_SUB_NO_UNCANCEL: a cancelled subscription can never be un-cancelled.
--
-- The Oracle trigger is BEFORE UPDATE OF status_cd FOR EACH ROW and does not raise: it
-- silently rewrites :NEW.status_cd back to 30 when the row was already 30, so the UPDATE
-- reports success and the row does not move. That silence is the observable behaviour and is
-- reproduced exactly - a RAISE here would be a new error path Oracle callers never see, and
-- pkg_plans.sp_change_plan depends on the rewrite (its DECODE(status_cd, 30, 30, 10) leans on
-- the same rule).
--
-- Postgres fires `UPDATE OF status_cd` on the same condition Oracle does: the column appears
-- in the SET list, whatever the value. Other columns (ends_on, suspended_on) update freely on
-- a cancelled row, as on Oracle.
CREATE OR REPLACE FUNCTION billing.trg_sub_no_uncancel()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status_cd = 30 THEN
        NEW.status_cd := 30;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sub_no_uncancel ON billing.subscriptions;
CREATE TRIGGER trg_sub_no_uncancel
    BEFORE UPDATE OF status_cd ON billing.subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION billing.trg_sub_no_uncancel();
