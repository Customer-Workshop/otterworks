-- ow_tp.gold.mv_overage — billed usage above plan entitlement, per tenant per period.
-- All arithmetic (entitlement, rollover cap, 101-unit tier break, 1.5x second tier,
-- suspension proration) is done once in fct_usage_period so a dashboard cannot re-derive
-- it differently. Periods with no rateable plan carry a NULL overage amount, which sums as
-- "excluded", and are counted by the Unrateable Periods measure so they stay visible.
CREATE OR REPLACE VIEW ow_tp.gold.mv_overage
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Usage above plan entitlement per tenant per month, priced with the legacy rating rules. Billable units = used - rollover - entitlement, floored at zero; first 101 units at the plan overage rate, the rest at 1.5x; prorated if the subscription was suspended inside the period."
source: ow_tp.gold.fct_usage_period
dimensions:
  - name: Period
    expr: period_month
  - name: Period Start
    expr: period_start
  - name: Plan
    expr: plan_code
  - name: Tenant
    expr: tenant_name
  - name: Subscription Status
    expr: CASE subscription_status_cd
        WHEN 10 THEN 'active'
        WHEN 20 THEN 'suspended'
        WHEN 30 THEN 'cancelled'
        ELSE 'no covering subscription'
      END
  - name: Over Entitlement
    expr: billable_units > 0
  - name: Prorated
    expr: proration_factor IS NOT NULL
measures:
  - name: Overage Amount
    expr: SUM(overage_amount)
    comment: "Billed overage in decimal currency"
  - name: Billable Units
    expr: SUM(billable_units)
  - name: Used Units
    expr: SUM(used_units)
  - name: Entitled Units
    expr: SUM(quota_units)
  - name: Rollover Units
    expr: SUM(rollover_units)
  - name: Utilisation
    expr: SUM(used_units) / NULLIF(SUM(quota_units), 0)
    comment: "Used units as a multiple of entitlement"
  - name: Tenants Over Entitlement
    expr: COUNT(DISTINCT CASE WHEN billable_units > 0 THEN tenant_id END)
  - name: Tenants
    expr: COUNT(DISTINCT tenant_id)
  - name: Unrateable Periods
    expr: COUNT_IF(overage_amount IS NULL)
    comment: "Tenant-periods with no covering subscription or no plan; never rated as free"
$$
