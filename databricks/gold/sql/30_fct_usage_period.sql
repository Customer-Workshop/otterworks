-- ow_tp.gold.fct_usage_period — usage rated against plan entitlement, per tenant per month.
--
-- This is the legacy PKG_RATING.compute_rating arithmetic, rewritten as set-based SQL and
-- kept deliberately faithful, including the parts nobody would design today:
--   * the period is a calendar month; used_units sums every usage kind (api, storage and
--     compute all count against one entitlement), as the legacy cursor loop does;
--   * the tenant's subscription is the latest-starting one overlapping the period
--     (starts_on <= period_end AND (ends_on IS NULL OR ends_on >= period_start));
--   * rollover is the prior three periods' banked units from the legacy rating results,
--     capped at twice the plan entitlement;
--   * billable = GREATEST(used - rollover - entitlement, 0);
--   * the price break sits at 101 units, not 100: the first 101 billable units go at the
--     plan overage rate and everything above it at 1.5x that rate. The legacy source calls
--     the 101 unexplained; changing it here would change the bill, so it stays;
--   * a subscription suspended inside the period prorates billable units and the overage
--     amount by the fraction of the period from the suspension date to period end.
-- A period with no covering subscription or no plan rates to zero billable units and a NULL
-- overage amount ("not rateable"), which is what the legacy NULL arithmetic produces; it is
-- never silently rated as if the plan were free.
--
-- Usage comes from ow_tp.silver.usage_events (TIMESTAMP_NTZ, zoneless as in Oracle), plans
-- and subscriptions from the Lakebase copies in ow_tp.gold. Money is DECIMAL throughout.
CREATE OR REPLACE TABLE ow_tp.gold.fct_usage_period
COMMENT 'Monthly usage rated against plan entitlement per tenant: used/rollover/billable units and overage amount, following the legacy PKG_RATING rules (101-unit tier break, 1.5x second tier, suspension proration).'
AS
WITH usage AS (
  SELECT
    u.tenant_id,
    CAST(DATE_TRUNC('MONTH', u.occurred_at) AS DATE)              AS period_start,
    LAST_DAY(CAST(u.occurred_at AS DATE))                         AS period_end,
    SUM(CAST(COALESCE(u.units, 0) AS BIGINT))                     AS used_units,
    SUM(CASE WHEN u.kind_cd = 1 THEN COALESCE(u.units, 0) ELSE 0 END) AS used_units_api,
    SUM(CASE WHEN u.kind_cd = 2 THEN COALESCE(u.units, 0) ELSE 0 END) AS used_units_storage,
    SUM(CASE WHEN u.kind_cd = 3 THEN COALESCE(u.units, 0) ELSE 0 END) AS used_units_compute,
    SUM(CASE WHEN u.kind_cd NOT IN (1, 2, 3) OR u.kind_cd IS NULL
             THEN COALESCE(u.units, 0) ELSE 0 END)                AS used_units_unknown_kind,
    COUNT(*)                                                      AS event_count
  FROM ow_tp.silver.usage_events u
  GROUP BY u.tenant_id, DATE_TRUNC('MONTH', u.occurred_at), LAST_DAY(CAST(u.occurred_at AS DATE))
),
covering AS (
  SELECT
    g.tenant_id, g.period_start, g.period_end,
    s.subscription_id, s.plan_id, s.status_cd, s.suspended_on,
    ROW_NUMBER() OVER (PARTITION BY g.tenant_id, g.period_start
                       ORDER BY s.starts_on DESC, s.subscription_id) AS rn
  FROM usage g
  JOIN ow_tp.gold.fct_subscription s
    ON s.tenant_id = g.tenant_id
   AND s.starts_on <= CAST(g.period_end AS TIMESTAMP_NTZ)
   AND (s.ends_on IS NULL OR s.ends_on >= CAST(g.period_start AS TIMESTAMP_NTZ))
),
rollover AS (
  -- Banked units from the three periods before this one, as the legacy engine recorded
  -- them. The migrated rating history only covers periods up to 2026-01, so this is 0 for
  -- every tenant in the current period rather than an estimate.
  SELECT g.tenant_id, g.period_start,
         SUM(COALESCE(r.rollover_units, 0)) AS prior_rollover_units
  FROM usage g
  JOIN ow_tp.gold.fct_rating_result r
    ON r.tenant_id = g.tenant_id
   AND CAST(r.period_start AS DATE) < g.period_start
   AND CAST(r.period_start AS DATE) >= ADD_MONTHS(g.period_start, -3)
  GROUP BY g.tenant_id, g.period_start
),
rated AS (
  SELECT
    g.tenant_id, g.period_start, g.period_end,
    g.used_units, g.used_units_api, g.used_units_storage, g.used_units_compute,
    g.used_units_unknown_kind, g.event_count,
    c.subscription_id, c.plan_id, c.status_cd AS subscription_status_cd, c.suspended_on,
    p.plan_code, p.included_units AS quota_units, p.overage_rate,
    LEAST(COALESCE(r.prior_rollover_units, 0),
          COALESCE(p.included_units * 2, COALESCE(r.prior_rollover_units, 0))) AS rollover_units
  FROM usage g
  LEFT JOIN covering c ON c.tenant_id = g.tenant_id AND c.period_start = g.period_start AND c.rn = 1
  LEFT JOIN ow_tp.gold.dim_plan p ON p.plan_id = c.plan_id
  LEFT JOIN rollover r ON r.tenant_id = g.tenant_id AND r.period_start = g.period_start
),
billed AS (
  SELECT
    rated.*,
    GREATEST(COALESCE(used_units - rollover_units - quota_units, 0), 0) AS billable_units_gross,
    CASE WHEN subscription_status_cd = 20 AND suspended_on IS NOT NULL
              AND CAST(suspended_on AS DATE) BETWEEN period_start AND period_end
         THEN CAST(DATEDIFF(period_end, CAST(suspended_on AS DATE)) + 1 AS DECIMAL(9,6))
              / CAST(DATEDIFF(period_end, period_start) + 1 AS DECIMAL(9,6))
    END AS proration_factor
  FROM rated
)
SELECT
  tenant_id,
  t.tenant_name,
  period_start,
  period_end,
  DATE_FORMAT(period_start, 'yyyy-MM')                       AS period_month,
  subscription_id,
  plan_id,
  plan_code,
  CAST(used_units AS BIGINT)                                 AS used_units,
  CAST(used_units_api AS BIGINT)                             AS used_units_api,
  CAST(used_units_storage AS BIGINT)                         AS used_units_storage,
  CAST(used_units_compute AS BIGINT)                         AS used_units_compute,
  CAST(used_units_unknown_kind AS BIGINT)                    AS used_units_unknown_kind,
  CAST(event_count AS BIGINT)                                AS event_count,
  CAST(quota_units AS BIGINT)                                AS quota_units,
  CAST(rollover_units AS BIGINT)                             AS rollover_units,
  CAST(overage_rate AS DECIMAL(12,6))                        AS overage_rate,
  subscription_status_cd,
  suspended_on,
  CAST(proration_factor AS DECIMAL(9,6))                     AS proration_factor,
  CAST(billable_units_gross AS BIGINT)                       AS billable_units_gross,
  CAST(ROUND(billable_units_gross * COALESCE(proration_factor, 1)) AS BIGINT) AS billable_units,
  -- two roundings, as in the legacy: the tiered amount is rounded to cents first, then the
  -- prorated amount is rounded again.
  CAST(ROUND(ROUND(LEAST(billable_units_gross, 101) * overage_rate
                   + GREATEST(billable_units_gross - 101, 0) * overage_rate * 1.5, 2)
             * COALESCE(proration_factor, 1), 2) AS DECIMAL(14,2)) AS overage_amount,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)                 AS built_at
FROM billed
LEFT JOIN ow_tp.gold.dim_tenant t USING (tenant_id)
