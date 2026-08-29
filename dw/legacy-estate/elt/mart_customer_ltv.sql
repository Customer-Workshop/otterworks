DELETE FROM mart.customer_ltv;

INSERT INTO mart.customer_ltv
    (customer_id, segment, first_order_date, last_order_date, order_count,
     lifetime_revenue, lifetime_discount, lifetime_net)
SELECT o.customer_id,
       UPPER(NVL(c.segment, 'UNKNOWN')),
       MIN(o.order_date),
       MAX(o.order_date),
       COUNT(*),
       SUM(o.gross_amount),
       SUM(o.discount_amount),
       SUM(o.gross_amount - o.discount_amount)
FROM core.fct_orders o
LEFT JOIN core.dim_customer_scd2 c
  ON c.customer_id = o.customer_id
 AND c.is_current
GROUP BY o.customer_id, UPPER(NVL(c.segment, 'UNKNOWN'));
