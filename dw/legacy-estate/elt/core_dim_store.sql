DELETE FROM core.dim_store;

INSERT INTO core.dim_store (store_id, store_name, store_type)
SELECT store_id,
       CASE WHEN store_id = 0 THEN 'Digital'
            ELSE 'Store ' || store_id::VARCHAR
       END,
       CASE WHEN store_id = 0 THEN 'DIGITAL' ELSE 'RETAIL' END
FROM (
    SELECT DISTINCT store_id
    FROM staging.stg_orders_raw
) stores;
