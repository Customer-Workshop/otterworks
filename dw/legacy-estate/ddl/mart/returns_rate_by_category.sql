CREATE TABLE IF NOT EXISTS mart.returns_rate_by_category (
    category         VARCHAR(40)   NOT NULL ENCODE bytedict,
    sold_items       BIGINT        ENCODE az64,
    returned_items   BIGINT        ENCODE az64,
    refund_amount    NUMERIC(18,2) ENCODE az64,
    return_rate_pct  NUMERIC(9,4)  ENCODE az64
)
DISTSTYLE ALL
SORTKEY (category);
