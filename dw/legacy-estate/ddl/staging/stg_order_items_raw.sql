-- Landing table for the OMS order line feed.
CREATE TABLE IF NOT EXISTS staging.stg_order_items_raw (
    order_item_id  BIGINT        NOT NULL ENCODE az64,
    order_id       BIGINT        NOT NULL ENCODE az64,
    product_id     BIGINT        NOT NULL ENCODE az64,
    quantity       INTEGER       ENCODE az64,
    unit_price     NUMERIC(12,2) ENCODE az64,
    item_discount  NUMERIC(12,2) ENCODE az64,
    line_amount    NUMERIC(12,2) ENCODE az64,
    load_ts        TIMESTAMP     ENCODE az64
)
DISTSTYLE KEY
DISTKEY (order_id)
COMPOUND SORTKEY (order_id, order_item_id);
