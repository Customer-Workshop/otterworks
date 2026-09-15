-- ow_tp.gold.fct_subscription_mrr — one row per subscription, priced as of a point in time.
--
-- ARR and MRR are run-rate metrics: what the book of business bills per month if nothing
-- changes, not revenue earned in a period. The table therefore has an `as_of_ts` and every
-- row is evaluated against it.
--
-- Active, written down rather than implied. A subscription counts towards MRR when all
-- three hold at `as_of_ts`:
--   1. status_cd = 10 (active). 20 suspended and 30 cancelled never count, even mid-period.
--   2. starts_on <= as_of_ts and (ends_on IS NULL OR ends_on >= as_of_ts). A NULL ends_on is
--      open-ended, as in the legacy PKG_PLANS lookup.
--   3. it is the latest-starting of that tenant's overlapping subscriptions
--      (ROW_NUMBER over starts_on DESC), which is how PKG_RATING and PKG_PLANS resolve a
--      tenant to one subscription. A mid-period plan change is therefore not prorated: the
--      new plan's full monthly fee replaces the old one from the instant it starts.
-- Rows that fail any of these stay in the table with mrr_amount = 0.00 so churn and
-- suspensions are visible rather than missing.
--
-- MRR = the plan's list monthly_fee. ARR = MRR * 12. Credit notes and usage overage do not
-- change either: see databricks/gold/METRIC_DEFINITIONS.md.
--
-- Money is DECIMAL end to end and timestamps are TIMESTAMP_NTZ (Oracle DATE carries a time
-- part; Oracle TIMESTAMP is zoneless), so no value is rounded through a float or shifted by
-- a session timezone.
CREATE OR REPLACE TABLE ow_tp.gold.fct_subscription_mrr
COMMENT 'Point-in-time subscription run rate: one row per subscription with MRR/ARR at as_of_ts. Active = status 10, period covers as_of_ts, latest-starting subscription for the tenant.'
AS
WITH params AS (
  -- as_of_ts is a job parameter. Empty (the default) means "now": a refresh with no
  -- argument prices the book at the moment it runs, and a backdated run is a parameter
  -- change rather than an edit to this statement. Only an empty value defaults; a value
  -- that is present but not a timestamp fails the run, because a backdated rebuild that
  -- quietly republishes today's book is worse than no rebuild.
  SELECT CASE
           WHEN NULLIF(:as_of_ts, '') IS NULL
             THEN CAST(current_timestamp() AS TIMESTAMP_NTZ)
           WHEN TRY_CAST(:as_of_ts AS TIMESTAMP_NTZ) IS NULL
             THEN raise_error(CONCAT('as_of_ts is not a timestamp: ', :as_of_ts))
           ELSE CAST(:as_of_ts AS TIMESTAMP_NTZ)
         END AS as_of_ts
),
ref_snapshot AS (
  -- The Lakebase reference load stamps every row of every reference table with one
  -- snapshot_id. The five tables are written by five statements, so a load that dies
  -- between them leaves plans from one read next to subscriptions from another. Pricing
  -- that mixture is worse than not refreshing: it fails the run instead. All five tables
  -- are checked, not just the ones MRR reads: this task runs first, so failing it stops
  -- the usage and storage builds downstream, which read credit notes and rating results.
  SELECT CASE
           WHEN COUNT(DISTINCT snapshot_id) > 1
             THEN raise_error(CONCAT(
                    'reference tables disagree on snapshot_id (',
                    CONCAT_WS(', ', COLLECT_SET(snapshot_id)),
                    '): rerun ingest_lakebase_reference.py'))
           ELSE MAX(snapshot_id)
         END AS snapshot_id
  FROM (SELECT snapshot_id FROM ow_tp.gold.dim_plan
        UNION SELECT snapshot_id FROM ow_tp.gold.fct_subscription
        UNION SELECT snapshot_id FROM ow_tp.gold.dim_tenant
        UNION SELECT snapshot_id FROM ow_tp.gold.fct_credit_note
        UNION SELECT snapshot_id FROM ow_tp.gold.fct_rating_result)
),
sub AS (
  SELECT
    s.subscription_id,
    s.tenant_id,
    s.plan_id,
    s.starts_on,
    s.ends_on,
    s.suspended_on,
    s.status_cd,
    p.as_of_ts,
    s.starts_on <= p.as_of_ts
      AND (s.ends_on IS NULL OR s.ends_on >= p.as_of_ts) AS covers_as_of
  FROM ow_tp.gold.fct_subscription s
  CROSS JOIN params p
  CROSS JOIN ref_snapshot g
),
ranked AS (
  SELECT
    sub.*,
    CASE WHEN covers_as_of THEN
      ROW_NUMBER() OVER (
        PARTITION BY CASE WHEN covers_as_of THEN tenant_id END
        ORDER BY starts_on DESC, subscription_id)
    END AS rn_latest_covering
  FROM sub
)
SELECT
  r.as_of_ts,
  r.subscription_id,
  r.tenant_id,
  t.tenant_name,
  t.status_cd                                     AS tenant_status_cd,
  tc.code_desc                                    AS tenant_status,
  r.plan_id,
  pl.plan_code,
  pl.tier_cd                                      AS plan_tier_cd,
  ti.code_desc                                    AS plan_tier,
  CAST(pl.monthly_fee AS DECIMAL(12,2))           AS plan_monthly_fee,
  CAST(pl.included_units AS BIGINT)               AS plan_included_units,
  CAST(pl.overage_rate AS DECIMAL(12,6))          AS plan_overage_rate,
  r.status_cd                                     AS subscription_status_cd,
  sc.code_desc                                    AS subscription_status,
  r.starts_on,
  r.ends_on,
  r.suspended_on,
  r.covers_as_of,
  r.rn_latest_covering = 1                        AS is_latest_for_tenant,
  r.status_cd = 10 AND r.covers_as_of
    AND r.rn_latest_covering = 1                  AS counts_towards_mrr,
  CAST(CASE WHEN r.status_cd = 10 AND r.covers_as_of AND r.rn_latest_covering = 1
            THEN pl.monthly_fee ELSE 0.00 END AS DECIMAL(12,2))      AS mrr_amount,
  CAST(CASE WHEN r.status_cd = 10 AND r.covers_as_of AND r.rn_latest_covering = 1
            THEN pl.monthly_fee * 12 ELSE 0.00 END AS DECIMAL(14,2)) AS arr_amount,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)      AS built_at
FROM ranked r
LEFT JOIN ow_tp.gold.dim_plan   pl ON pl.plan_id = r.plan_id
LEFT JOIN ow_tp.gold.dim_tenant t  ON t.tenant_id = r.tenant_id
LEFT JOIN ow_tp.bronze.codes sc ON sc.code_type = 'SUB_STATUS'    AND sc.code_val = r.status_cd
LEFT JOIN ow_tp.bronze.codes tc ON tc.code_type = 'TENANT_STATUS' AND tc.code_val = t.status_cd
LEFT JOIN ow_tp.bronze.codes ti ON ti.code_type = 'PLAN_TIER'     AND ti.code_val = pl.tier_cd
