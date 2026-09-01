-- Rebuild the baseline period dimension before each full-snapshot load.
DROP TABLE IF EXISTS ow_tp.silver.dim_period_cdw;

CREATE TABLE ow_tp.silver.dim_period_cdw (
    period_key BIGINT NOT NULL,
    period_month STRING NOT NULL,
    year_num INT NOT NULL,
    month_num INT NOT NULL,
    quarter_num INT NOT NULL,
    loaded_at TIMESTAMP NOT NULL
) USING DELTA;

INSERT INTO ow_tp.silver.dim_period_cdw
SELECT period_key, period_month, year_num, month_num, quarter_num, current_timestamp()
FROM read_files(
    '/Volumes/ow_tp/bronze/landing/cdw/baseline/DIM_PERIOD.csv',
    format => 'csv',
    header => true,
    schema => 'period_key BIGINT, period_month STRING, year_num INT, month_num INT, quarter_num INT',
    mode => 'FAILFAST'
);
