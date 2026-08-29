-- Fiscal calendar dimension.
CREATE TABLE IF NOT EXISTS core.dim_date (
    date_key       DATE        NOT NULL ENCODE az64,
    calendar_year  INTEGER     ENCODE az64,
    calendar_month INTEGER     ENCODE az64,
    month_name     VARCHAR(12) ENCODE bytedict,
    calendar_day   INTEGER     ENCODE az64,
    day_of_week    INTEGER     ENCODE az64,
    day_name       VARCHAR(12) ENCODE bytedict,
    week_of_year   INTEGER     ENCODE az64,
    quarter_num    INTEGER     ENCODE az64,
    fiscal_year    INTEGER     ENCODE az64,
    fiscal_quarter INTEGER     ENCODE az64,
    is_weekend     BOOLEAN     ENCODE raw,
    PRIMARY KEY (date_key)
)
DISTSTYLE ALL
SORTKEY (date_key);
