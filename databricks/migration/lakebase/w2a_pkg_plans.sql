-- U-21 pkg_plans -> Lakebase PL/pgSQL (unit p1-pkg-plans, wave 2 batch a).
--
-- Oracle source: services/legacy-billing/db/oracle/packages/02_pkg_plans.sql (read-only).
-- Idempotent: CREATE OR REPLACE only (P1-D6); this script creates no table.
--
-- Declared write targets for this unit: billing.fn_plan_entitlements, billing.sp_assign_plan
-- and billing.subscriptions (written by the procedure). Nothing else is created here.
--
-- Entrypoint coverage: the package has three entrypoints. `fn_entitlement` and
-- `sp_change_plan` are the two below. `fn_list_plans` (a plans-only projection) is NOT in
-- this unit's declared write targets and is not created here - it is reported as a coverage
-- gap rather than written to an undeclared object.

-- fn_plan_entitlements: pkg_plans.fn_entitlement.
--
-- Oracle returns a SYS_REFCURSOR over a fixed seven-column projection; the projection is the
-- consumer contract and is reproduced column for column, in order, with the same names.
--
-- Conversions:
--   * `p.id (+) = s.plan_id` (old-style comma join with the outer-join operator) becomes
--     LEFT JOIN plans, keeping subscriptions as the preserved side: a subscription whose
--     plan_id has no plans row still returns, with NULL plan_code / fee (D8-01 orphans).
--     `tenants` is joined inner, as Oracle's unmarked `s.tenant_id = t.id` is.
--   * `ROWNUM <= 1` over an ordered inline view becomes ORDER BY ... DESC LIMIT 1. Ties on
--     starts_on resolve arbitrarily on both platforms; the source does not order further.
--   * DECODE becomes CASE. Unknown codes keep the literal 'UNKNOWN' the source returns.
--
-- Package state (P1-D4): Oracle caches the last lookup in the package globals
-- g_last_tenant_id / g_last_plan_code, which any session-mate can read and which nothing
-- invalidates. A Postgres function has no session global to hide them in, and P1-D4 forbids
-- re-creating one, so the cache write is returned explicitly as the last_tenant_id /
-- last_plan_code columns: what Oracle stashed out of band, the caller now receives in band.
-- The lookup itself is the source's own second query (no tenants join, NVL(ends_on,
-- '31-DEC-99'), ROWNUM = 1, unordered), and its `WHEN OTHERS THEN NULL` stays swallowed
-- (P1-D2): a failed lookup yields NULL, never an error.
--
-- NOT reproduced, and declared rather than fixed: Oracle's cache survives the call, so a
-- later caller can read a previous caller's plan code. Reproducing that staleness needs a
-- state row, and a state table is outside this unit's declared write targets - the batch may
-- write only subscriptions, fn_plan_entitlements and sp_assign_plan. Recorded as a coverage
-- gap for the owner instead of written to an undeclared object.
CREATE OR REPLACE FUNCTION billing.fn_plan_entitlements(p_tenant_id text, p_on timestamp)
RETURNS TABLE (
    tenant_id           varchar(36),
    plan_code           varchar(50),
    tier                text,
    monthly_fee         numeric(12,2),
    included_units      bigint,
    subscription_status text,
    effective_on        timestamp(0),
    last_tenant_id      varchar(36),
    last_plan_code      varchar(50)
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_last_tenant_id varchar(36) := p_tenant_id;   -- Oracle assigns this unconditionally
    v_last_plan_code varchar(50);
BEGIN
    BEGIN
        SELECT p.code
          INTO v_last_plan_code
          FROM billing.subscriptions s
          LEFT JOIN billing.plans p ON p.id = s.plan_id
         WHERE s.tenant_id = p_tenant_id
           AND s.starts_on <= p_on
           AND COALESCE(s.ends_on, timestamp '2099-12-31 00:00:00') >= p_on
         LIMIT 1;
    EXCEPTION
        WHEN OTHERS THEN
            v_last_plan_code := NULL;   -- WHEN OTHERS THEN NULL, reproduced (P1-D2)
    END;

    RETURN QUERY
    SELECT t.id                            AS tenant_id,
           p.code                          AS plan_code,
           CASE p.tier_cd WHEN 1 THEN 'starter' WHEN 2 THEN 'growth' WHEN 3 THEN 'scale'
                          ELSE 'UNKNOWN' END                          AS tier,
           p.monthly_fee,
           p.included_units,
           CASE s.status_cd WHEN 10 THEN 'active' WHEN 20 THEN 'suspended'
                            WHEN 30 THEN 'cancelled' ELSE 'UNKNOWN' END AS subscription_status,
           GREATEST(s.starts_on, p_on)::timestamp(0)                  AS effective_on,
           v_last_tenant_id,
           v_last_plan_code
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

COMMENT ON FUNCTION billing.fn_plan_entitlements(text, timestamp) IS
    'Migration unit p1-pkg-plans (U-21) from Oracle pkg_plans.fn_entitlement. '
    'last_tenant_id/last_plan_code are the explicit form of the package globals (P1-D4).';

-- sp_assign_plan: pkg_plans.sp_change_plan.
--
-- Conversions:
--   * The cursor keeps FOR UPDATE and the row-by-row close-out keeps WHERE CURRENT OF, so
--     the locking semantics are the source's: the open subscriptions are locked for the life
--     of the transaction and each row is updated through its own cursor position. The
--     set-based rewrite would be faster and would not hold the same locks, which is why it
--     is not used here.
--   * DECODE(r.status_cd, 30, 30, 10) becomes CASE. The rule it leans on -
--     "cancelled stays cancelled" - is enforced by trg_sub_no_uncancel on the table, exactly
--     as on Oracle; the CASE is the source's belt to that braces.
--   * `p_effective_on - 1` on an Oracle DATE is minus one day, so it is INTERVAL '1 day' on
--     a timestamp, not a numeric subtraction.
--   * The EXECUTE IMMEDIATE around a perfectly static INSERT becomes a plain INSERT with the
--     same column list, the same bind order and the same literal status 10.
--   * The audit line keeps the source's text, including the Oracle member name, so the
--     billing_audit_log rows compare byte for byte.
--
-- NOT reproduced here, and out of this unit's declared write targets: Oracle's
-- TRG_SUBSCRIPTIONS_HIST writes a SUBSCRIPTIONS_HIST row for every UPDATE below. That table
-- belongs to unit p1-subscriptions-hist; the history rows this procedure causes on Oracle
-- have no target rows until that unit lands.
CREATE OR REPLACE PROCEDURE billing.sp_assign_plan(p_tenant_id text, p_plan_id text,
                                                   p_effective_on timestamp)
LANGUAGE plpgsql
AS $$
DECLARE
    c_open_subs CURSOR FOR
        SELECT id, status_cd
          FROM billing.subscriptions
         WHERE tenant_id = p_tenant_id
           AND ends_on IS NULL
           AND starts_on < p_effective_on
           FOR UPDATE;
    r        record;
    v_new_id varchar(36);
BEGIN
    PERFORM billing.log_msg('PLANS', 'sp_change_plan tenant=' || p_tenant_id ||
        ' plan=' || p_plan_id || ' eff=' || to_char(p_effective_on, 'YYYY-MM-DD'));

    OPEN c_open_subs;
    LOOP
        FETCH c_open_subs INTO r;
        EXIT WHEN NOT FOUND;
        UPDATE billing.subscriptions
           SET ends_on = p_effective_on - INTERVAL '1 day',
               status_cd = CASE WHEN r.status_cd = 30 THEN 30 ELSE 10 END
         WHERE CURRENT OF c_open_subs;
    END LOOP;
    CLOSE c_open_subs;

    v_new_id := billing.f_md5_uuid(
        p_tenant_id || p_plan_id || to_char(p_effective_on, 'YYYY-MM-DD'));

    INSERT INTO billing.subscriptions (id, tenant_id, plan_id, starts_on, status_cd)
    VALUES (v_new_id, p_tenant_id, p_plan_id, p_effective_on, 10);
END;
$$;

COMMENT ON PROCEDURE billing.sp_assign_plan(text, text, timestamp) IS
    'Migration unit p1-pkg-plans (U-21) from Oracle pkg_plans.sp_change_plan.';
