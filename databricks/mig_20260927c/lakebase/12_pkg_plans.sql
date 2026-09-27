-- Run 20260927c, unit pkg_plans: OW_BILLING.PKG_PLANS + TRG_SUBSCRIPTIONS_HIST + TRG_SUB_NO_UNCANCEL -> billing.*.
-- Source: services/legacy-billing/db/oracle/packages/02_pkg_plans.sql, schema/01_tables.sql.
-- Package state (g_last_tenant_id, g_last_plan_code) has no reader outside the package and is dropped.
-- DATE parameters arrive as timestamp (Oracle DATE -> timestamp(0), D-010/DEP-016).

-- TRG_SUBSCRIPTIONS_HIST: full-row copy of :OLD on UPDATE/DELETE; hist_dt is TO_CHAR(SYSDATE,'DD-MON-YY HH24:MI:SS').
CREATE OR REPLACE FUNCTION billing.trg_subscriptions_hist()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO billing.subscriptions_hist (
        hist_dt, hist_op, id, tenant_id, plan_id, starts_on, ends_on, status_cd, suspended_on
    ) VALUES (
        to_char(localtimestamp, 'DD-MON-YY HH24:MI:SS'),
        CASE WHEN TG_OP = 'UPDATE' THEN 'UPD' ELSE 'DEL' END,
        OLD.id, OLD.tenant_id, OLD.plan_id, OLD.starts_on, OLD.ends_on, OLD.status_cd, OLD.suspended_on
    );
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_subscriptions_hist ON billing.subscriptions;
CREATE TRIGGER trg_subscriptions_hist
AFTER UPDATE OR DELETE ON billing.subscriptions
FOR EACH ROW EXECUTE FUNCTION billing.trg_subscriptions_hist();

-- TRG_SUB_NO_UNCANCEL: a cancelled (30) subscription never leaves the cancelled state.
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
FOR EACH ROW EXECUTE FUNCTION billing.trg_sub_no_uncancel();

CREATE OR REPLACE FUNCTION billing.fn_list_plans()
RETURNS TABLE (
    plan_id        varchar,
    code           varchar,
    tier           varchar,
    monthly_fee    numeric,
    included_units bigint,
    overage_rate   numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    CALL billing.log_msg('PLANS', 'fn_list_plans');
    RETURN QUERY
        SELECT p.id, p.code,
               CASE p.tier_cd WHEN 1 THEN 'starter' WHEN 2 THEN 'growth' WHEN 3 THEN 'scale'
                    ELSE 'UNKNOWN' END::varchar,
               p.monthly_fee, p.included_units, p.overage_rate
          FROM billing.plans p
         WHERE coalesce(p.active_yn, 'N') = 'Y'
         ORDER BY p.monthly_fee, p.code COLLATE "C";
END;
$$;

CREATE OR REPLACE FUNCTION billing.fn_entitlement(p_tenant_id varchar, p_on timestamp)
RETURNS TABLE (
    tenant_id           varchar,
    plan_code           varchar,
    tier                varchar,
    monthly_fee         numeric,
    included_units      bigint,
    subscription_status varchar,
    effective_on        timestamp
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
        SELECT t.id, p.code,
               CASE p.tier_cd WHEN 1 THEN 'starter' WHEN 2 THEN 'growth' WHEN 3 THEN 'scale'
                    ELSE 'UNKNOWN' END::varchar,
               p.monthly_fee, p.included_units,
               CASE s.status_cd WHEN 10 THEN 'active' WHEN 20 THEN 'suspended' WHEN 30 THEN 'cancelled'
                    ELSE 'UNKNOWN' END::varchar,
               greatest(s.starts_on, p_on)
          FROM billing.tenants t
          JOIN billing.subscriptions s ON s.tenant_id = t.id
          LEFT JOIN billing.plans p ON p.id = s.plan_id
         WHERE t.id = p_tenant_id
           AND s.starts_on <= p_on
           AND (s.ends_on IS NULL OR s.ends_on >= p_on)
         ORDER BY s.starts_on DESC
         LIMIT 1;
END;
$$;

CREATE OR REPLACE PROCEDURE billing.sp_change_plan(p_tenant_id varchar, p_plan_id varchar, p_effective_on timestamp)
LANGUAGE plpgsql
AS $$
DECLARE
    r        record;
    v_new_id varchar(36);
BEGIN
    CALL billing.log_msg('PLANS', 'sp_change_plan tenant=' || p_tenant_id ||
        ' plan=' || p_plan_id || ' eff=' || to_char(p_effective_on, 'YYYY-MM-DD'));
    FOR r IN
        SELECT id, status_cd
          FROM billing.subscriptions
         WHERE tenant_id = p_tenant_id
           AND ends_on IS NULL
           AND starts_on < p_effective_on
         FOR UPDATE
    LOOP
        UPDATE billing.subscriptions
           SET ends_on = p_effective_on - interval '1 day',
               status_cd = CASE r.status_cd WHEN 30 THEN 30 ELSE 10 END
         WHERE id = r.id;
    END LOOP;
    v_new_id := billing.f_md5_uuid(p_tenant_id || p_plan_id || to_char(p_effective_on, 'YYYY-MM-DD'));
    INSERT INTO billing.subscriptions (id, tenant_id, plan_id, starts_on, status_cd)
    VALUES (v_new_id, p_tenant_id, p_plan_id, p_effective_on, 10);
END;
$$;
