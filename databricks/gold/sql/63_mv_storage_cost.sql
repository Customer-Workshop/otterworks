-- ow_tp.gold.mv_storage_cost — storage cost per tenant.
-- Two measures on purpose. Allocated Storage Cost is storage's share of money actually
-- billed, so it ties back to the overage total. Storage Cost At List prices storage units
-- at the plan overage rate as if entitlement did not exist, which is a unit-economics view
-- and does not tie to revenue. Picking one and hiding the other is how a storage number
-- ends up indefensible, so both are published with their definitions attached.
CREATE OR REPLACE VIEW ow_tp.gold.mv_storage_cost
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Storage cost per tenant per month. The estate prices only units above entitlement, and storage shares one entitlement with api and compute, so storage cost is either its share of billed overage (ties to revenue) or storage units at the plan overage rate (does not)."
source: ow_tp.gold.fct_storage_cost_tenant
dimensions:
  - name: Period
    expr: period_month
  - name: Period Start
    expr: period_start
  - name: Plan
    expr: plan_code
  - name: Tenant
    expr: tenant_name
  - name: Storage Heavy
    expr: storage_unit_share > 0.5
    comment: "Storage is more than half of the tenant's metered units in the period"
measures:
  - name: Allocated Storage Cost
    expr: SUM(storage_cost_allocated)
    comment: "Share of the tenant's billed overage attributable to storage units"
  - name: Storage Cost At List
    expr: SUM(storage_cost_at_list)
    comment: "Storage units * plan overage rate, ignoring entitlement and tiering"
  - name: Storage Units
    expr: SUM(storage_units)
  - name: Total Metered Units
    expr: SUM(used_units)
  - name: Storage Share
    expr: SUM(storage_units) / NULLIF(SUM(used_units), 0)
  - name: Period Overage
    expr: SUM(period_overage_amount)
    comment: "Total billed overage for the same rows, so the allocation can be checked"
  - name: Tenants
    expr: COUNT(DISTINCT tenant_id)
  - name: Cost Per Storage Unit
    expr: SUM(storage_cost_allocated) / NULLIF(SUM(storage_units), 0)
$$
