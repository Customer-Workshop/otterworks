CREATE TABLE IF NOT EXISTS mart.product_performance_monthly (
    revenue_month  DATE          NOT NULL ENCODE az64,
    product_id     BIGINT        NOT NULL ENCODE az64,
    product_name   VARCHAR(160)  ENCODE lzo,
    category       VARCHAR(40)   ENCODE bytedict,
    units_sold     BIGINT        ENCODE az64,
    order_count    BIGINT        ENCODE az64,
    revenue        NUMERIC(18,2) ENCODE az64,
    margin         NUMERIC(18,2) ENCODE az64
)
DISTSTYLE KEY
DISTKEY (product_id)
SORTKEY (revenue_month, category, product_id);
