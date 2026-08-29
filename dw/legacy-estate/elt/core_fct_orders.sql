DELETE FROM core.fct_orders;

INSERT INTO core.fct_orders
    (order_id, customer_id, order_ts, order_date, channel, store_id,
     currency_code, order_status, gross_amount, discount_amount,
     shipping_amount, tax_amount, net_amount, promo_code, source_file,
     load_ts)
SELECT order_id,
       customer_id,
       order_ts,
       order_ts::DATE,
       channel,
       store_id,
       currency_code,
       order_status,
       gross_amount,
       discount_amount,
       shipping_amount,
       tax_amount,
       gross_amount - discount_amount + shipping_amount + tax_amount,
       promo_code,
       source_file,
       load_ts
FROM (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY load_ts DESC,
                        source_file DESC,
                        order_ts DESC,
                        gross_amount DESC
           ) AS row_num
    FROM staging.stg_orders_raw o
) ranked
WHERE row_num = 1;
