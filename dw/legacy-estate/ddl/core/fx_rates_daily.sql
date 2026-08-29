-- Daily FX rates, including forward-filled gaps.
CREATE TABLE IF NOT EXISTS core.fx_rates_daily (
    rate_date      DATE         NOT NULL ENCODE az64,
    currency_code  CHAR(3)      NOT NULL ENCODE bytedict,
    rate_to_usd    NUMERIC(18,6) ENCODE az64,
    rate_source    VARCHAR(16)  ENCODE bytedict,
    load_ts        TIMESTAMP    ENCODE az64,
    PRIMARY KEY (rate_date, currency_code)
)
DISTSTYLE ALL
COMPOUND SORTKEY (rate_date, currency_code);
