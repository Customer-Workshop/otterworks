CREATE TABLE IF NOT EXISTS mart.customer_ltv (
    customer_id       BIGINT        NOT NULL ENCODE az64,
    segment           VARCHAR(20)   ENCODE bytedict,
    first_order_date  DATE          ENCODE az64,
    last_order_date   DATE          ENCODE az64,
    order_count       BIGINT        ENCODE az64,
    lifetime_revenue  NUMERIC(18,2) ENCODE az64,
    lifetime_discount NUMERIC(18,2) ENCODE az64,
    lifetime_net      NUMERIC(18,2) ENCODE az64,
    PRIMARY KEY (customer_id)
)
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (segment, customer_id);
