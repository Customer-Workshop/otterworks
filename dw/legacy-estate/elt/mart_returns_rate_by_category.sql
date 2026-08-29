DELETE FROM mart.returns_rate_by_category;

INSERT INTO mart.returns_rate_by_category
    (category, sold_items, returned_items, refund_amount, return_rate_pct)
WITH sold AS (
    SELECT category, COUNT(*) AS sold_items
    FROM core.fct_order_items
    GROUP BY category
),
returned AS (
    SELECT category,
           COUNT(*) AS returned_items,
           SUM(refund_amount) AS refund_amount
    FROM core.fct_returns
    GROUP BY category
)
SELECT s.category,
       s.sold_items,
       NVL(r.returned_items, 0),
       NVL(r.refund_amount, 0),
       ROUND(NVL(r.returned_items, 0)::NUMERIC / NULLIF(s.sold_items, 0), 4)
FROM sold s
LEFT JOIN returned r ON r.category = s.category;
