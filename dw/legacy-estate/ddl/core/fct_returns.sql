-- Returns joined to the originating order-line and product.
CREATE TABLE IF NOT EXISTS core.fct_returns (
    return_id      BIGINT        NOT NULL ENCODE az64,
    order_id       BIGINT        NOT NULL ENCODE az64,
    order_item_id  BIGINT        NOT NULL ENCODE az64,
    product_id     BIGINT        NOT NULL ENCODE az64,
    category       VARCHAR(40)   ENCODE bytedict,
    return_ts      TIMESTAMP     ENCODE az64,
    return_date    DATE          ENCODE az64,
    reason_code    VARCHAR(24)   ENCODE bytedict,
    refund_amount  NUMERIC(12,2) ENCODE az64,
    currency_code  CHAR(3)       ENCODE bytedict,
    load_ts        TIMESTAMP     ENCODE az64,
    PRIMARY KEY (return_id)
)
DISTSTYLE KEY
DISTKEY (order_id)
COMPOUND SORTKEY (return_date, return_id);
