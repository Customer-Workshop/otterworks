-- Landing table for the returns/RMA feed.
CREATE TABLE IF NOT EXISTS staging.stg_returns_raw (
    return_id      BIGINT        NOT NULL ENCODE az64,
    order_id       BIGINT        NOT NULL ENCODE az64,
    order_item_id  BIGINT        NOT NULL ENCODE az64,
    return_ts      TIMESTAMP     ENCODE az64,
    reason_code    VARCHAR(24)   ENCODE bytedict,
    refund_amount  NUMERIC(12,2) ENCODE az64,
    load_ts        TIMESTAMP     ENCODE az64
)
DISTSTYLE KEY
DISTKEY (order_id)
COMPOUND SORTKEY (return_ts, return_id);
