DELETE FROM core.fct_order_items;

INSERT INTO core.fct_order_items
    (order_item_id, order_id, customer_id, order_date, channel, product_id,
     product_name, category, subcategory, brand, quantity, unit_price,
     item_discount, line_amount, cost_amount, margin_amount, currency_code,
     is_returned, load_ts)
SELECT i.order_item_id,
       i.order_id,
       o.customer_id,
       o.order_date,
       o.channel,
       i.product_id,
       p.product_name,
       p.category,
       p.subcategory,
       p.brand,
       i.quantity,
       i.unit_price,
       i.item_discount,
       i.line_amount,
       ROUND(p.unit_cost * i.quantity, 2),
       ROUND(i.line_amount - (p.unit_cost * i.quantity), 2),
       o.currency_code,
       EXISTS (
           SELECT 1
           FROM staging.stg_returns_raw r
           WHERE r.order_item_id = i.order_item_id
       ),
       i.load_ts
FROM staging.stg_order_items_raw i
JOIN core.fct_orders o ON o.order_id = i.order_id
JOIN core.dim_product p ON p.product_id = i.product_id;
