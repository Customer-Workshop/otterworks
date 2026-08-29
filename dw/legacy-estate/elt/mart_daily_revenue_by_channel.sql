DELETE FROM mart.daily_revenue_by_channel;

INSERT INTO mart.daily_revenue_by_channel
    (order_date, channel, order_count, gross_revenue, discount_total,
     net_revenue)
SELECT order_date,
       channel,
       COUNT(*),
       SUM(gross_amount),
       SUM(discount_amount),
       SUM(gross_amount - discount_amount)
FROM core.fct_orders
GROUP BY order_date, channel;
