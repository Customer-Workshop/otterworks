CREATE TABLE IF NOT EXISTS mart.top_products_by_category (
    category          VARCHAR(40)   NOT NULL ENCODE bytedict,
    top_product_count INTEGER       ENCODE az64,
    product_names     VARCHAR(2000) ENCODE lzo,
    top_revenue       NUMERIC(18,2) ENCODE az64
)
DISTSTYLE ALL
SORTKEY (category);
