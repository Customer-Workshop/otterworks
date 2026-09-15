-- ow_tp.gold.fct_storage_cost_tenant — cost of storage usage per tenant per month.
--
-- The estate has no storage price. Plans price one thing only: units above entitlement, at
-- plan.overage_rate, and storage events (usage kind 2) consume the same entitlement as api
-- and compute. So "storage cost" cannot be read off a rate card and has to be stated as a
-- rule. Two numbers are published side by side, and neither is a guess dressed as a fact:
--
--   storage_cost_allocated  — the tenant's actual billed overage for the period, split
--                             across usage kinds in proportion to units. This is the only
--                             figure that sums back to money the business really bills:
--                             SUM(storage) + SUM(api) + SUM(compute) = SUM(overage_amount).
--                             A tenant inside entitlement therefore has 0.00 storage cost
--                             even with real storage usage, because nothing was billed.
--   storage_cost_at_list    — storage units * plan overage_rate, ignoring entitlement,
--                             rollover and tiering. Useful as a unit-economics view of
--                             storage on its own; it does not tie to billed revenue.
--
-- Allocation is by raw unit share, not by which units "arrived last": the legacy engine has
-- no notion of ordering within a period, so any sequencing rule would be invented here.
-- Rounding is to cents on the allocated share, so the three kinds can differ from the
-- period overage by at most 0.01; the residual is carried on the largest kind so the
-- allocation stays exact. A period with no rateable plan has NULL costs, not 0.00.
CREATE OR REPLACE TABLE ow_tp.gold.fct_storage_cost_tenant
COMMENT 'Storage cost per tenant per month. storage_cost_allocated splits actually-billed overage across usage kinds by unit share (ties back to billed revenue); storage_cost_at_list prices storage units at the plan overage rate ignoring entitlement.'
AS
WITH base AS (
  SELECT
    u.tenant_id,
    u.tenant_name,
    u.period_start,
    u.period_end,
    u.period_month,
    u.plan_id,
    u.plan_code,
    u.overage_rate,
    u.quota_units,
    u.used_units,
    u.used_units_storage,
    u.used_units_api,
    u.used_units_compute,
    u.billable_units,
    u.overage_amount,
    CASE WHEN u.used_units > 0
         THEN CAST(u.used_units_storage AS DECIMAL(18,6)) / CAST(u.used_units AS DECIMAL(18,6))
         ELSE CAST(0 AS DECIMAL(18,6)) END AS storage_unit_share
  FROM ow_tp.gold.fct_usage_period u
),
alloc AS (
  SELECT
    base.*,
    CAST(ROUND(overage_amount * storage_unit_share, 2) AS DECIMAL(14,2)) AS storage_cost_raw,
    CAST(ROUND(overage_amount * (CAST(used_units_api AS DECIMAL(18,6))
         / NULLIF(CAST(used_units AS DECIMAL(18,6)), 0)), 2) AS DECIMAL(14,2)) AS api_cost_raw,
    CAST(ROUND(overage_amount * (CAST(used_units_compute AS DECIMAL(18,6))
         / NULLIF(CAST(used_units AS DECIMAL(18,6)), 0)), 2) AS DECIMAL(14,2)) AS compute_cost_raw
  FROM base
)
SELECT
  tenant_id,
  tenant_name,
  period_start,
  period_end,
  period_month,
  plan_id,
  plan_code,
  CAST(quota_units AS BIGINT)                          AS quota_units,
  CAST(used_units AS BIGINT)                           AS used_units,
  CAST(used_units_storage AS BIGINT)                   AS storage_units,
  CAST(storage_unit_share AS DECIMAL(9,6))             AS storage_unit_share,
  CAST(billable_units AS BIGINT)                       AS billable_units,
  CAST(overage_amount AS DECIMAL(14,2))                AS period_overage_amount,
  -- residual from cent-rounding lands on the largest kind so the three allocations add up
  -- to period_overage_amount exactly
  CAST(CASE
    WHEN overage_amount IS NULL THEN NULL
    WHEN used_units_storage >= used_units_api AND used_units_storage >= used_units_compute
      THEN overage_amount - COALESCE(api_cost_raw, 0) - COALESCE(compute_cost_raw, 0)
    ELSE storage_cost_raw
  END AS DECIMAL(14,2))                                AS storage_cost_allocated,
  CAST(ROUND(used_units_storage * overage_rate, 2) AS DECIMAL(14,2)) AS storage_cost_at_list,
  CAST(overage_rate AS DECIMAL(12,6))                  AS overage_rate,
  CAST(current_timestamp() AS TIMESTAMP_NTZ)           AS built_at
FROM alloc
