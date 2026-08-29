-- Order-line fact enriched with the current product and order attributes.
CREATE TABLE IF NOT EXISTS core.fct_order_items (
    order_item_id    BIGINT        NOT NULL ENCODE az64,
    order_id         BIGINT        NOT NULL ENCODE az64,
    customer_id      BIGINT        NOT NULL ENCODE az64,
    order_date       DATE          ENCODE az64,
    channel          VARCHAR(20)   ENCODE bytedict,
    product_id       BIGINT        NOT NULL ENCODE az64,
    product_name     VARCHAR(160)  ENCODE lzo,
    category         VARCHAR(40)   ENCODE bytedict,
    subcategory      VARCHAR(60)   ENCODE bytedict,
    brand            VARCHAR(60)   ENCODE bytedict,
    quantity         INTEGER       ENCODE az64,
    unit_price       NUMERIC(12,2) ENCODE az64,
    item_discount    NUMERIC(12,2) ENCODE az64,
    line_amount      NUMERIC(12,2) ENCODE az64,
    cost_amount      NUMERIC(12,2) ENCODE az64,
    margin_amount    NUMERIC(12,2) ENCODE az64,
    currency_code    CHAR(3)       ENCODE bytedict,
    is_returned      BOOLEAN       ENCODE raw,
    load_ts          TIMESTAMP     ENCODE az64,
    PRIMARY KEY (order_item_id)
)
DISTSTYLE KEY
DISTKEY (order_id)
COMPOUND SORTKEY (order_date, order_id, order_item_id);
