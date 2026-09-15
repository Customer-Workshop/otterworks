-- U-22 pkg_rating -> Lakebase PL/pgSQL (unit p1-pkg-rating, wave 4 batch d).
--
-- Oracle source: services/legacy-billing/db/oracle/packages/03_pkg_rating.sql (read-only).
-- Idempotent: CREATE OR REPLACE only (P1-D6); this script creates no table.
--
-- Declared write targets for this unit: billing.fn_usage_rating, billing.fn_usage_summary and
-- billing.sp_finalize_rating. Runtime DML only into tables earlier waves own the DDL for:
-- billing.rating_periods, billing.rating_results, billing.rating_state and (through log_msg)
-- billing.billing_audit_log. Nothing else is created, altered or written here.
--
-- Entrypoint coverage: the package exposes three entrypoints plus the internal compute_rating.
-- All three entrypoints are below. compute_rating is not a separate object here - a fourth
-- object is outside the declared write targets - so it lives inside fn_usage_rating, which is
-- how Oracle's own fn_usage_rating reaches it, and sp_finalize_rating calls fn_usage_rating
-- for exactly the values Oracle reads back out of the package globals.
--
-- TRG_USAGE_EVENTS_CHECK (services/legacy-billing/db/oracle/schema/01_tables.sql): a BEFORE
-- INSERT trigger on usage_events rejecting units <= 0 and unknown kind_cd. It is NOT converted
-- here and this unit does not need it: pkg_rating only reads usage_events. Creating it would
-- be DDL on billing.usage_events, which unit p1-usage-events-oltp (w4-c) owns and which is
-- outside this batch's declared write targets. Carried forward as a coverage gap for the
-- owner, not routed around.

-- fn_usage_rating: pkg_rating.fn_usage_rating, with compute_rating inlined.
--
-- Oracle returns a SYS_REFCURSOR over the ten package globals compute_rating just set; the
-- projection is the consumer contract and is reproduced column for column, in order, with the
-- same names.
--
-- Package state (P1-D4): compute_rating's results are session globals on Oracle, and
-- sp_finalize_rating (and, later, pkg_invoicing) read them out of band. Here they are the
-- function's own result columns, and the one value that crosses a call boundary,
-- g_overage_amount, is written to billing.rating_state by sp_finalize_rating. No hidden
-- session state is recreated.
--
-- Conversions:
--   * `ROWNUM <= 1` over an ordered inline view becomes ORDER BY starts_on DESC LIMIT 1, and
--     the `WHEN NO_DATA_FOUND THEN NULL` around it is what plpgsql's SELECT INTO already does:
--     no row leaves the variables NULL and the rating continues.
--   * The usage cursor stays a row-at-a-time loop with the source's
--     TO_CHAR(..., 'YYYYMMDD') string comparison, not a set-based SUM over a timestamp range:
--     the string compare is the behaviour under test, and a rewrite would change which rows
--     land in the period at the boundaries.
--   * ADD_MONTHS(p_period_start, -3) is not `- interval '3 months'`. Oracle keeps the
--     last-day-of-month property (ADD_MONTHS('28-FEB-26', -3) is 30-NOV-25, not 28-NOV-25);
--     Postgres only clamps an overflow. Both rules are applied below, so the rollover window
--     starts on the same instant as Oracle's for a period that starts on a month end.
--   * LEAST/GREATEST differ on NULL - Oracle propagates, Postgres ignores - which the source
--     itself flags at :95-98. Every operand here is made non-NULL by the source's own NVL, so
--     the two agree; the one place where the source does pass a NULL operand is the
--     rating_results rollover expression in sp_finalize_rating, handled there.
--   * Money and units stay numeric. ROUND stays exactly where the source puts it: once on the
--     tiered overage, and again per-branch inside the suspension proration.
--   * Oracle DATE subtraction yields days as a number; timestamp subtraction yields an
--     interval, so the proration factor divides EXTRACT(EPOCH ...) / 86400 to get the same
--     fractional days.
--   * Oracle reads an empty VARCHAR2 as NULL and Postgres does not, so the tenant id is
--     normalised with NULLIF and the audit text is built with concat(), which folds NULL to ''
--     the way Oracle's `||` does.
CREATE OR REPLACE FUNCTION billing.fn_usage_rating(p_tenant_id text, p_period_start timestamp,
                                                   p_period_end timestamp)
RETURNS TABLE (
    tenant_id         varchar(36),
    period_start      timestamp(0),
    period_end        timestamp(0),
    used_units        numeric,
    quota_units       numeric,
    rollover_units    numeric,
    billable_units    numeric,
    first_tier_units  numeric,
    second_tier_units numeric,
    overage_amount    numeric
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_tenant_id    text := NULLIF(p_tenant_id, '');
    v_sub_id       varchar(36);
    v_sub_status   smallint;
    v_suspended_on timestamp;
    v_plan_id      varchar(36);
    v_included     numeric;
    v_rate         numeric;
    v_prior        numeric := 0;
    v_factor       numeric;
    v_window_start timestamp;
    v_used         numeric := 0;
    v_quota        numeric;
    v_rollover     numeric;
    v_billable     numeric;
    v_first        numeric;
    v_second       numeric;
    v_overage      numeric;
    r              record;
BEGIN
    SELECT s.id, s.status_cd, s.suspended_on, s.plan_id
      INTO v_sub_id, v_sub_status, v_suspended_on, v_plan_id
      FROM billing.subscriptions s
     WHERE s.tenant_id = v_tenant_id
       AND s.starts_on <= p_period_end
       AND (s.ends_on IS NULL OR s.ends_on >= p_period_start)
     ORDER BY s.starts_on DESC
     LIMIT 1;

    SELECT p.included_units, p.overage_rate
      INTO v_included, v_rate
      FROM billing.plans p
     WHERE p.id = v_plan_id;

    -- The period's usage, one row at a time, string-comparing the event date as the source does.
    FOR r IN SELECT u.units, u.occurred_at
               FROM billing.usage_events u
              WHERE u.tenant_id = v_tenant_id LOOP
        IF to_char(r.occurred_at, 'YYYYMMDD') >= to_char(p_period_start, 'YYYYMMDD')
           AND to_char(r.occurred_at, 'YYYYMMDD') <= to_char(p_period_end, 'YYYYMMDD') THEN
            v_used := v_used + COALESCE(r.units, 0);
        END IF;
    END LOOP;

    -- ADD_MONTHS(p_period_start, -3), Oracle's last-day rule included.
    v_window_start := CASE
        WHEN p_period_start::date
             = (date_trunc('month', p_period_start) + interval '1 month - 1 day')::date
        THEN (date_trunc('month', p_period_start::date - interval '3 months')
              + interval '1 month - 1 day')::date
             + (p_period_start - date_trunc('day', p_period_start))
        ELSE p_period_start - interval '3 months'
    END;

    -- Rollover credit: prior three months of banked units, capped twice to the same number.
    FOR r IN SELECT rr.rollover_units
               FROM billing.rating_results rr
               JOIN billing.rating_periods rp ON rp.id = rr.period_id
              WHERE rp.tenant_id = v_tenant_id
                AND rp.period_start < p_period_start
                AND rp.period_start >= v_window_start LOOP
        v_prior := v_prior + COALESCE(r.rollover_units, 0);
    END LOOP;
    v_prior := LEAST(COALESCE(2 * v_included, v_prior), v_prior);

    v_quota := v_included;
    v_rollover := LEAST(v_prior, COALESCE(v_included * 2, v_prior));
    v_billable := GREATEST(COALESCE(v_used - v_rollover - v_included, 0), 0);
    -- Tier break at 101 units, as in the source.
    v_first := LEAST(v_billable, 101);
    v_second := GREATEST(v_billable - 101, 0);
    v_overage := round(v_first * v_rate + v_second * v_rate * 1.5, 2);

    IF v_sub_status = 20 AND v_suspended_on IS NOT NULL
       AND v_suspended_on BETWEEN p_period_start AND p_period_end THEN
        v_factor := (extract(epoch FROM (p_period_end - v_suspended_on)) / 86400 + 1)
                  / (extract(epoch FROM (p_period_end - p_period_start)) / 86400 + 1);
        v_billable := round(v_billable * v_factor);
        v_overage := round(v_overage * v_factor, 2);
    END IF;

    PERFORM billing.log_msg('RATING', concat('compute tenant=', v_tenant_id,
        ' used=', COALESCE(v_used, -1)::text,
        ' billable=', COALESCE(v_billable, -1)::text));

    RETURN QUERY
    SELECT v_tenant_id::varchar(36),
           p_period_start::timestamp(0),
           p_period_end::timestamp(0),
           v_used, v_quota, v_rollover, v_billable, v_first, v_second, v_overage;
END;
$$;

COMMENT ON FUNCTION billing.fn_usage_rating(text, timestamp, timestamp) IS
    'Migration unit p1-pkg-rating (U-22) from Oracle pkg_rating.fn_usage_rating, with '
    'compute_rating inlined. The package globals are the result columns (P1-D4); the audit '
    'row compute_rating writes is kept (D-009).';

-- fn_usage_summary: pkg_rating.fn_usage_summary.
--
-- Conversions: DECODE becomes CASE with the same literals, including 'UNKNOWN' for a kind_cd
-- outside 1/2/3; the BETWEEN stays a string comparison of TO_CHAR(..., 'YYYYMMDD'); the GROUP
-- BY repeats the expression as the source does and ORDER BY 1 orders on the mapped label.
-- Status/kind codes stay magic numbers.
CREATE OR REPLACE FUNCTION billing.fn_usage_summary(p_tenant_id text, p_period_start timestamp,
                                                    p_period_end timestamp)
RETURNS TABLE (
    kind        text,
    event_count bigint,
    units       numeric
)
LANGUAGE sql
STABLE
AS $$
    SELECT CASE u.kind_cd WHEN 1 THEN 'api' WHEN 2 THEN 'storage' WHEN 3 THEN 'compute'
                          ELSE 'UNKNOWN' END AS kind,
           COUNT(*)                          AS event_count,
           COALESCE(SUM(u.units), 0)::numeric AS units
      FROM billing.usage_events u
     WHERE u.tenant_id = NULLIF(p_tenant_id, '')
       AND to_char(u.occurred_at, 'YYYYMMDD')
               BETWEEN to_char(p_period_start, 'YYYYMMDD')
                   AND to_char(p_period_end, 'YYYYMMDD')
     GROUP BY CASE u.kind_cd WHEN 1 THEN 'api' WHEN 2 THEN 'storage' WHEN 3 THEN 'compute'
                             ELSE 'UNKNOWN' END
     ORDER BY 1;
$$;

COMMENT ON FUNCTION billing.fn_usage_summary(text, timestamp, timestamp) IS
    'Migration unit p1-pkg-rating (U-22) from Oracle pkg_rating.fn_usage_summary.';

-- sp_finalize_rating: pkg_rating.sp_finalize_rating.
--
-- Conversions:
--   * The insert-then-catch-DUP_VAL_ON_INDEX upserts stay insert-then-catch, on
--     unique_violation, rather than becoming ON CONFLICT: the source's UPDATE branches do not
--     touch the same columns the INSERT does (rating_periods updates only period_end;
--     rating_results leaves quota_units and created_at alone), and ON CONFLICT would quietly
--     change what a second finalize of the same period writes.
--   * rating_results.rollover_units is written from GREATEST(quota - used, 0), NOT from the
--     rollover the rating computed. That is what the source stores, in both the INSERT and the
--     UPDATE, and it is preserved verbatim. Because Oracle's GREATEST propagates NULL and
--     Postgres' does not, a tenant with no covering plan must produce NULL here - which the
--     NOT NULL column then rejects, as ORA-01400 does on Oracle - so the NULL operand is made
--     explicit instead of silently becoming 0.
--   * compute_rating's ten globals arrive as the fn_usage_rating row; the audit row that call
--     writes is the source's own (D-009) and stays.
--   * billing.rating_state is the explicit form of the g_overage_amount hand-off to
--     pkg_invoicing (P1-D4). Oracle leaves the value in a session global; here the finalize
--     writes it, keyed by (tenant_id, period_id), with a zoneless updated_at (D-010).
--   * CAST(p_period_end AS TIMESTAMP) is a plain timestamp on both sides.
CREATE OR REPLACE PROCEDURE billing.sp_finalize_rating(p_tenant_id text,
                                                       p_period_start timestamp,
                                                       p_period_end timestamp)
LANGUAGE plpgsql
AS $$
DECLARE
    v_tenant_id text := NULLIF(p_tenant_id, '');
    v_period_id varchar(36);
    v_result_id varchar(36);
    v_sub_id    varchar(36);
    v_rating    record;
    v_rollover  numeric;
BEGIN
    v_period_id := billing.f_md5_uuid(
        concat(v_tenant_id, to_char(p_period_start, 'YYYY-MM-DD')));

    SELECT s.id
      INTO v_sub_id
      FROM billing.subscriptions s
     WHERE s.tenant_id = v_tenant_id
       AND s.starts_on <= p_period_end
       AND (s.ends_on IS NULL OR s.ends_on >= p_period_start)
     ORDER BY s.starts_on DESC
     LIMIT 1;

    BEGIN
        INSERT INTO billing.rating_periods (id, tenant_id, period_start, period_end)
        VALUES (v_period_id, v_tenant_id, p_period_start, p_period_end);
    EXCEPTION
        WHEN unique_violation THEN
            UPDATE billing.rating_periods
               SET period_end = p_period_end
             WHERE tenant_id = v_tenant_id
               AND period_start = p_period_start;
    END;

    SELECT * INTO v_rating
      FROM billing.fn_usage_rating(v_tenant_id, p_period_start, p_period_end);

    v_rollover := CASE
        WHEN v_rating.quota_units IS NULL OR v_rating.used_units IS NULL THEN NULL
        ELSE GREATEST(v_rating.quota_units - v_rating.used_units, 0)
    END;

    v_result_id := billing.f_md5_uuid(v_period_id);
    BEGIN
        INSERT INTO billing.rating_results (
            id, period_id, subscription_id, used_units, quota_units,
            rollover_units, billable_units, overage_amount, created_at
        ) VALUES (
            v_result_id, v_period_id, v_sub_id, v_rating.used_units, v_rating.quota_units,
            v_rollover, v_rating.billable_units, v_rating.overage_amount,
            p_period_end::timestamp
        );
    EXCEPTION
        WHEN unique_violation THEN
            UPDATE billing.rating_results
               SET used_units = v_rating.used_units,
                   rollover_units = v_rollover,
                   billable_units = v_rating.billable_units,
                   overage_amount = v_rating.overage_amount
             WHERE id = v_result_id;
    END;

    INSERT INTO billing.rating_state (tenant_id, period_id, overage_amount, finalized, updated_at)
    VALUES (v_tenant_id, v_period_id, v_rating.overage_amount, true, localtimestamp)
    ON CONFLICT (tenant_id, period_id) DO UPDATE
       SET overage_amount = EXCLUDED.overage_amount,
           finalized      = true,
           updated_at     = localtimestamp;

    PERFORM billing.log_msg('RATING', concat('finalized period=', v_period_id));
END;
$$;

COMMENT ON PROCEDURE billing.sp_finalize_rating(text, timestamp, timestamp) IS
    'Migration unit p1-pkg-rating (U-22) from Oracle pkg_rating.sp_finalize_rating. '
    'Writes billing.rating_state, the explicit g_overage_amount hand-off (P1-D4).';
