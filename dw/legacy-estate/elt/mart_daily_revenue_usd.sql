DELETE FROM mart.daily_revenue_usd;

INSERT INTO mart.daily_revenue_usd
    (order_date, channel, currency_code, order_count, revenue_native,
     fx_rate, revenue_usd)
SELECT o.order_date,
       o.channel,
       o.currency_code,
       COUNT(*),
       SUM(o.gross_amount - o.discount_amount),
       fx.rate_to_usd,
       ROUND(SUM(o.gross_amount - o.discount_amount) * fx.rate_to_usd, 2)
FROM core.fct_orders o
JOIN core.fx_rates_daily fx
  ON fx.rate_date = o.order_date
 AND fx.currency_code = o.currency_code
GROUP BY o.order_date, o.channel, o.currency_code, fx.rate_to_usd;
