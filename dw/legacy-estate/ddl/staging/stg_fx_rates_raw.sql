-- Daily FX reference feed (rate to USD). Small dimension, replicated to every node.
CREATE TABLE IF NOT EXISTS staging.stg_fx_rates_raw (
    rate_date      DATE          NOT NULL ENCODE az64,
    currency_code  CHAR(3)       NOT NULL ENCODE bytedict,
    rate_to_usd    NUMERIC(18,6) ENCODE az64,
    load_ts        TIMESTAMP     ENCODE az64
)
DISTSTYLE ALL
COMPOUND SORTKEY (rate_date, currency_code);
