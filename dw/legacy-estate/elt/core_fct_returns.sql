DELETE FROM core.fct_returns;

INSERT INTO core.fct_returns
    (return_id, order_id, order_item_id, product_id, category, return_ts,
     return_date, reason_code, refund_amount, currency_code, load_ts)
SELECT r.return_id,
       r.order_id,
       r.order_item_id,
       i.product_id,
       i.category,
       r.return_ts,
       r.return_ts::DATE,
       r.reason_code,
       r.refund_amount,
       o.currency_code,
       r.load_ts
FROM staging.stg_returns_raw r
JOIN core.fct_order_items i ON i.order_item_id = r.order_item_id
JOIN core.fct_orders o ON o.order_id = r.order_id;
