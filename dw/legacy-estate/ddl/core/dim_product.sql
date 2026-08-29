-- Current product dimension (SCD1).
CREATE TABLE IF NOT EXISTS core.dim_product (
    product_id   BIGINT        NOT NULL ENCODE az64,
    product_name VARCHAR(160)  ENCODE lzo,
    category     VARCHAR(40)   ENCODE bytedict,
    subcategory  VARCHAR(60)   ENCODE bytedict,
    brand        VARCHAR(60)   ENCODE bytedict,
    unit_cost    NUMERIC(12,2) ENCODE az64,
    list_price   NUMERIC(12,2) ENCODE az64,
    is_active    BOOLEAN       ENCODE raw,
    supplier_id  INTEGER       ENCODE az64,
    load_ts      TIMESTAMP     ENCODE az64,
    PRIMARY KEY (product_id)
)
DISTSTYLE ALL
SORTKEY (category, product_id);
