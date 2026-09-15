-- ow_tp.gold.mv_arr_mrr — governed ARR and MRR, by plan or any other subscription cut.
-- Serves both "ARR" and "MRR by plan": grouping by `Plan` gives MRR by plan, grouping by
-- nothing gives company ARR/MRR, and every consumer gets the same active-subscription rule
-- because the rule lives in fct_subscription_mrr, not in each query.
CREATE OR REPLACE VIEW ow_tp.gold.mv_arr_mrr
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Subscription run rate. ARR = MRR * 12. A subscription counts when status = active, its period covers as_of_ts, and it is the tenant's latest-starting covering subscription. Credit notes and usage overage do not change ARR or MRR."
source: ow_tp.gold.fct_subscription_mrr
dimensions:
  - name: Plan
    expr: plan_code
    comment: "Plan code the subscription is priced on"
  - name: Plan Tier
    expr: plan_tier
  - name: Subscription Status
    expr: subscription_status
    comment: "active / suspended / cancelled, from the legacy SUB_STATUS code set"
  - name: Tenant Status
    expr: tenant_status
  - name: Tenant
    expr: tenant_name
  - name: Counts Towards MRR
    expr: counts_towards_mrr
    comment: "False rows are retained so churn and suspensions stay visible"
  - name: As Of
    expr: as_of_ts
  - name: Starts Month
    expr: DATE_TRUNC('MONTH', starts_on)
measures:
  - name: MRR
    expr: SUM(mrr_amount)
    comment: "Monthly recurring revenue in decimal currency"
  - name: ARR
    expr: SUM(arr_amount)
    comment: "MRR * 12"
  - name: Active Subscriptions
    expr: COUNT_IF(counts_towards_mrr)
  - name: Subscriptions
    expr: COUNT(1)
  - name: Paying Tenants
    expr: COUNT(DISTINCT CASE WHEN counts_towards_mrr THEN tenant_id END)
  - name: ARPA
    expr: SUM(mrr_amount) / NULLIF(COUNT(DISTINCT CASE WHEN counts_towards_mrr THEN tenant_id END), 0)
    comment: "Average monthly revenue per paying tenant"
$$
