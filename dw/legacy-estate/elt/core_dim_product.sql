DELETE FROM core.dim_product;

INSERT INTO core.dim_product
    (product_id, product_name, category, subcategory, brand, unit_cost,
     list_price, is_active, supplier_id, load_ts)
SELECT product_id,
       product_name,
       category,
       subcategory,
       brand,
       unit_cost,
       list_price,
       is_active,
       supplier_id,
       load_ts
FROM staging.stg_products_raw;
