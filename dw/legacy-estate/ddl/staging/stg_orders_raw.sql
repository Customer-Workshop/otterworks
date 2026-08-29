-- Landing table for the OMS order header feed. One row per order per delivered file;
-- re-delivered files are appended, so this table is NOT unique on order_id.
CREATE TABLE IF NOT EXISTS staging.stg_orders_raw (
    order_id         BIGINT        NOT NULL ENCODE az64,
    customer_id      BIGINT        NOT NULL ENCODE az64,
    order_ts         TIMESTAMP     ENCODE az64,
    channel          VARCHAR(20)   ENCODE bytedict,
    store_id         INTEGER       ENCODE az64,
    currency_code    CHAR(3)       ENCODE bytedict,
    order_status     VARCHAR(20)   ENCODE bytedict,
    gross_amount     NUMERIC(12,2) ENCODE az64,
    discount_amount  NUMERIC(12,2) ENCODE az64,
    shipping_amount  NUMERIC(12,2) ENCODE az64,
    tax_amount       NUMERIC(12,2) ENCODE az64,
    promo_code       VARCHAR(24)   ENCODE lzo,
    source_file      VARCHAR(80)   ENCODE lzo,
    load_ts          TIMESTAMP     ENCODE az64
)
DISTSTYLE KEY
DISTKEY (order_id)
COMPOUND SORTKEY (order_ts, order_id);
