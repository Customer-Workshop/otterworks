-- Run 20260927c, unit pkg_rating: OW_BILLING.PKG_RATING -> billing.* (PL/pgSQL).
-- Source: services/legacy-billing/db/oracle/packages/03_pkg_rating.sql.
-- The package globals (g_*) that compute_rating publishes for fn_usage_rating / compute_preview /
-- sp_finalize_rating become the OUT record of billing.compute_rating; callers read that record.
-- Oracle NULL semantics kept explicitly: NVL -> coalesce; LEAST/GREATEST return NULL when any argument
-- is NULL (Postgres ignores NULLs), so every such call is spelled out as a CASE.
-- ROUND on NUMBER is half away from zero: all arithmetic stays in numeric (round(numeric) matches).

CREATE OR REPLACE FUNCTION billing.compute_rating(
    p_tenant_id       varchar,
    p_period_start    timestamp,
    p_period_end      timestamp,
    OUT tenant_id         varchar,
    OUT period_start      timestamp,
    OUT period_end        timestamp,
    OUT used_units        bigint,
    OUT quota_units       bigint,
    OUT rollover_units    bigint,
    OUT billable_units    bigint,
    OUT first_tier_units  bigint,
    OUT second_tier_units bigint,
    OUT overage_amount    numeric
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_sub_id       varchar(36);
    v_sub_status   bigint;
    v_suspended_on timestamp;
    v_plan_id      varchar(36);
    v_included     numeric := NULL;
    v_rate         numeric := NULL;
    v_prior        numeric := 0;
    v_used         numeric := 0;
    v_rollover     numeric;
    v_billable     numeric;
    v_first        numeric;
    v_second       numeric;
    v_overage      numeric;
    v_factor       numeric;
    v_window_start timestamp;
BEGIN
    tenant_id := p_tenant_id;
    period_start := p_period_start;
    period_end := p_period_end;

    SELECT s.id, s.status_cd, s.suspended_on, s.plan_id
      INTO v_sub_id, v_sub_status, v_suspended_on, v_plan_id
      FROM billing.subscriptions s
     WHERE s.tenant_id = p_tenant_id
       AND s.starts_on <= p_period_end
       AND (s.ends_on IS NULL OR s.ends_on >= p_period_start)
     ORDER BY s.starts_on DESC
     LIMIT 1;

    SELECT p.included_units, p.overage_rate INTO v_included, v_rate
      FROM billing.plans p WHERE p.id = v_plan_id;

    -- TO_CHAR(occurred_at,'YYYYMMDD') BETWEEN ... : calendar-day comparison
    SELECT coalesce(sum(coalesce(u.units, 0)), 0) INTO v_used
      FROM billing.usage_events u
     WHERE u.tenant_id = p_tenant_id
       AND u.occurred_at::date >= p_period_start::date
       AND u.occurred_at::date <= p_period_end::date;

    -- ADD_MONTHS(p_period_start, -3): a last-day-of-month input lands on the last day of the target month
    v_window_start := p_period_start - interval '3 months';
    IF p_period_start::date = (date_trunc('month', p_period_start) + interval '1 month - 1 day')::date THEN
        v_window_start := (date_trunc('month', v_window_start) + interval '1 month - 1 day')
                          + (p_period_start - p_period_start::date);
    END IF;
    SELECT coalesce(sum(coalesce(rr.rollover_units, 0)), 0) INTO v_prior
      FROM billing.rating_results rr
      JOIN billing.rating_periods rp ON rp.id = rr.period_id
     WHERE rp.tenant_id = p_tenant_id
       AND rp.period_start < p_period_start
       AND rp.period_start >= v_window_start;

    -- v_prior := LEAST(NVL(2*v_included, v_prior), v_prior)
    v_prior := least(coalesce(2 * v_included, v_prior), v_prior);
    quota_units := v_included;
    -- g_rollover := LEAST(v_prior, NVL(v_included*2, v_prior))
    v_rollover := least(v_prior, coalesce(v_included * 2, v_prior));
    -- g_billable := GREATEST(NVL(used - rollover - included, 0), 0)
    v_billable := greatest(coalesce(v_used - v_rollover - v_included, 0), 0);
    v_first := least(v_billable, 101);
    v_second := greatest(v_billable - 101, 0);
    -- ROUND(first*rate + second*rate*1.5, 2): NULL when the rate is NULL (no plan)
    v_overage := CASE WHEN v_rate IS NULL THEN NULL
                      ELSE round(v_first * v_rate + v_second * v_rate * 1.5, 2) END;

    IF v_sub_status = 20 AND v_suspended_on IS NOT NULL
       AND v_suspended_on BETWEEN p_period_start AND p_period_end THEN
        v_factor := (extract(epoch FROM (p_period_end - v_suspended_on)) / 86400 + 1) /
                    (extract(epoch FROM (p_period_end - p_period_start)) / 86400 + 1);
        v_billable := round(v_billable * v_factor);
        v_overage := round(v_overage * v_factor, 2);
    END IF;

    used_units := v_used;
    rollover_units := v_rollover;
    billable_units := v_billable;
    first_tier_units := v_first;
    second_tier_units := v_second;
    overage_amount := v_overage;

    CALL billing.log_msg('RATING', 'compute tenant=' || p_tenant_id ||
        ' used=' || regexp_replace(regexp_replace(regexp_replace((coalesce(v_used, -1))::text, '(\.\d*?)0+$', '\1'), '\.$', ''), '^(-?)0\.', '\1.') ||
        ' billable=' || regexp_replace(regexp_replace(regexp_replace((coalesce(v_billable, -1))::text, '(\.\d*?)0+$', '\1'), '\.$', ''), '^(-?)0\.', '\1.'));
END;
$$;

CREATE OR REPLACE FUNCTION billing.fn_usage_rating(p_tenant_id varchar, p_period_start timestamp, p_period_end timestamp)
RETURNS TABLE (
    tenant_id         varchar,
    period_start      timestamp,
    period_end        timestamp,
    used_units        bigint,
    quota_units       bigint,
    rollover_units    bigint,
    billable_units    bigint,
    first_tier_units  bigint,
    second_tier_units bigint,
    overage_amount    numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY SELECT * FROM billing.compute_rating(p_tenant_id, p_period_start, p_period_end);
END;
$$;

CREATE OR REPLACE FUNCTION billing.fn_usage_summary(p_tenant_id varchar, p_period_start timestamp, p_period_end timestamp)
RETURNS TABLE (
    kind        varchar,
    event_count bigint,
    units       numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
        SELECT k.kind, count(*)::bigint, coalesce(sum(u.units), 0)::numeric
          FROM billing.usage_events u
          CROSS JOIN LATERAL (SELECT CASE u.kind_cd WHEN 1 THEN 'api' WHEN 2 THEN 'storage' WHEN 3 THEN 'compute'
                                     ELSE 'UNKNOWN' END::varchar AS kind) k
         WHERE u.tenant_id = p_tenant_id
           AND u.occurred_at::date BETWEEN p_period_start::date AND p_period_end::date
         GROUP BY k.kind
         ORDER BY k.kind COLLATE "C";
END;
$$;

CREATE OR REPLACE PROCEDURE billing.sp_finalize_rating(p_tenant_id varchar, p_period_start timestamp, p_period_end timestamp)
LANGUAGE plpgsql
AS $$
DECLARE
    v_period_id varchar(36);
    v_result_id varchar(36);
    v_sub_id    varchar(36);
    g           record;
    v_rollover  bigint;
BEGIN
    v_period_id := billing.f_md5_uuid(p_tenant_id || to_char(p_period_start, 'YYYY-MM-DD'));

    SELECT s.id INTO v_sub_id
      FROM billing.subscriptions s
     WHERE s.tenant_id = p_tenant_id
       AND s.starts_on <= p_period_end
       AND (s.ends_on IS NULL OR s.ends_on >= p_period_start)
     ORDER BY s.starts_on DESC
     LIMIT 1;

    BEGIN
        INSERT INTO billing.rating_periods (id, tenant_id, period_start, period_end)
        VALUES (v_period_id, p_tenant_id, p_period_start, p_period_end);
    EXCEPTION
        WHEN unique_violation THEN
            UPDATE billing.rating_periods
               SET period_end = p_period_end
             WHERE tenant_id = p_tenant_id
               AND period_start = p_period_start;
    END;

    SELECT * INTO g FROM billing.compute_rating(p_tenant_id, p_period_start, p_period_end);
    v_result_id := billing.f_md5_uuid(v_period_id);
    -- GREATEST(g_quota_units - g_used_units, 0): NULL when quota is NULL
    v_rollover := CASE WHEN g.quota_units IS NULL THEN NULL ELSE greatest(g.quota_units - g.used_units, 0) END;

    BEGIN
        INSERT INTO billing.rating_results (
            id, period_id, subscription_id, used_units, quota_units,
            rollover_units, billable_units, overage_amount, created_at
        ) VALUES (
            v_result_id, v_period_id, v_sub_id, g.used_units, g.quota_units,
            v_rollover, g.billable_units, g.overage_amount, p_period_end::timestamp(6)
        );
    EXCEPTION
        WHEN unique_violation THEN
            UPDATE billing.rating_results
               SET used_units = g.used_units,
                   rollover_units = v_rollover,
                   billable_units = g.billable_units,
                   overage_amount = g.overage_amount
             WHERE id = v_result_id;
    END;

    CALL billing.log_msg('RATING', 'finalized period=' || v_period_id);
END;
$$;
