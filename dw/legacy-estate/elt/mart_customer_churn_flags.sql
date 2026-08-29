-- Churn flags for the lifecycle email campaign. The campaign moved to the
-- vendor's own scoring model, so this mart is no longer refreshed by any job.

DELETE FROM mart.customer_churn_flags;

INSERT INTO mart.customer_churn_flags
    (customer_id, last_order_date, days_since_order, churn_flag, calculated_at)
SELECT c.customer_id,
       MAX(o.order_ts)::DATE,
       DATEDIFF(day, MAX(o.order_ts), GETDATE()),
       CASE WHEN DATEDIFF(day, MAX(o.order_ts), GETDATE()) > 90 THEN TRUE
            ELSE FALSE END,
       GETDATE()
FROM core.dim_customer_scd2 c
LEFT JOIN core.fct_orders o ON o.customer_id = c.customer_id
WHERE c.is_current = TRUE
GROUP BY c.customer_id;
