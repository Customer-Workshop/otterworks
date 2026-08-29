CREATE TABLE IF NOT EXISTS mart.daily_revenue_usd (
    order_date      DATE          NOT NULL ENCODE az64,
    channel         VARCHAR(20)   NOT NULL ENCODE bytedict,
    currency_code   CHAR(3)       NOT NULL ENCODE bytedict,
    order_count     BIGINT        ENCODE az64,
    revenue_native  NUMERIC(18,2) ENCODE az64,
    fx_rate         NUMERIC(18,6) ENCODE az64,
    revenue_usd     NUMERIC(18,2) ENCODE az64
)
DISTSTYLE KEY
DISTKEY (order_date)
SORTKEY (order_date, channel, currency_code);
