CREATE TABLE IF NOT EXISTS mart.daily_revenue_by_channel (
    order_date      DATE          NOT NULL ENCODE az64,
    channel         VARCHAR(20)   NOT NULL ENCODE bytedict,
    order_count     BIGINT        ENCODE az64,
    gross_revenue   NUMERIC(18,2) ENCODE az64,
    discount_total  NUMERIC(18,2) ENCODE az64,
    net_revenue     NUMERIC(18,2) ENCODE az64
)
DISTSTYLE KEY
DISTKEY (order_date)
SORTKEY (order_date, channel);
