-- DW_ETL_PKG.LOAD_COMMISSION_FACTS, dim_product MERGE
-- (services/industry-solutions/insurance/db/olap/02_etl_pkg.sql L35-44) -> Databricks SQL.
-- Runs after ddl.sql against a freshly created table. Statements are executed in order;
-- any failure aborts the run (no error swallowing).

-- 1. Initialise from the COMMISSION_DW baseline snapshot: explicit product_key values (DEC-003).
--    UTF-8 CSV, header row, explicit schema, FAILFAST on any malformed record; empty field = NULL.
INSERT INTO ow_tp.silver.dim_product_cdw (product_key, product_code, product_name, line_of_business, loaded_at)
SELECT product_key, product_code, product_name, line_of_business, current_timestamp()
FROM read_files(
    '/Volumes/ow_tp/bronze/landing/cdw/baseline/DIM_PRODUCT.csv',
    format => 'csv', header => true,
    schema => 'product_key BIGINT, product_code STRING, product_name STRING, line_of_business STRING',
    mode => 'FAILFAST'
);

-- 2. Feed guard: the legacy columns are NOT NULL; Spark would insert NULLs where Oracle raised.
SELECT assert_true(
    count_if(product_code IS NULL OR product_name IS NULL OR line_of_business IS NULL) = 0,
    'products_cdw feed contains NULL product_code/product_name/line_of_business'
) FROM ow_tp.bronze.products_cdw;

-- 3. The converted MERGE: same ON key, same UPDATE column list, same INSERT column list.
--    New rows receive max(product_key) + row_number() OVER (ORDER BY product_code), computed only
--    over the rows that do not match (the identity sequence only advanced on inserts).
MERGE INTO ow_tp.silver.dim_product_cdw d
USING (
    SELECT s.product_code,
           s.product_name,
           s.line_of_business,
           CASE WHEN x.product_code IS NULL
                THEN k.max_key + row_number() OVER (PARTITION BY (x.product_code IS NULL) ORDER BY s.product_code)
           END AS new_product_key
    FROM ow_tp.bronze.products_cdw s
    LEFT JOIN ow_tp.silver.dim_product_cdw x ON x.product_code = s.product_code
    CROSS JOIN (SELECT coalesce(max(product_key), 0) AS max_key FROM ow_tp.silver.dim_product_cdw) k
) s
ON d.product_code = s.product_code
WHEN MATCHED THEN UPDATE SET
    d.product_name     = s.product_name,
    d.line_of_business = s.line_of_business
WHEN NOT MATCHED THEN INSERT (product_key, product_code, product_name, line_of_business, loaded_at)
    VALUES (s.new_product_key, s.product_code, s.product_name, s.line_of_business, current_timestamp());
