DELETE FROM mart.product_performance_monthly;

INSERT INTO mart.product_performance_monthly
    (revenue_month, product_id, product_name, category, units_sold,
     order_count, revenue, margin)
SELECT DATE_TRUNC('month', order_date)::DATE,
       product_id,
       product_name,
       category,
       SUM(quantity),
       COUNT(DISTINCT order_id),
       SUM(line_amount),
       SUM(margin_amount)
FROM core.fct_order_items
GROUP BY DATE_TRUNC('month', order_date)::DATE,
         product_id, product_name, category;
