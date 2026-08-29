DELETE FROM mart.top_products_by_category;

INSERT INTO mart.top_products_by_category
    (category, top_product_count, product_names, top_revenue)
WITH product_totals AS (
    SELECT category,
           product_id,
           MAX(product_name) AS product_name,
           SUM(line_amount) AS revenue,
           ROW_NUMBER() OVER (
               PARTITION BY category
               ORDER BY SUM(line_amount) DESC, product_id
           ) AS product_rank
    FROM core.fct_order_items
    GROUP BY category, product_id
),
top_products AS (
    SELECT category, product_id, product_name, revenue
    FROM product_totals
    WHERE product_rank <= 5
)
SELECT category,
       COUNT(*),
       LISTAGG(product_name, ', ') WITHIN GROUP (ORDER BY revenue DESC, product_id),
       SUM(revenue)
FROM top_products
GROUP BY category;
