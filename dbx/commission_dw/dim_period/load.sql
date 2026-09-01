-- Reject a source volume that differs from the manifest declaration.
SELECT assert_true(
    count(*) = {{declared_feed_rows}},
    'ledger feed row count differs from declared source volume'
)
FROM ow_tp.bronze.commission_ledger_cdw;

-- Spark casts malformed values to NULL where Oracle TO_NUMBER raises.
SELECT assert_true(
    count_if(
        year_num IS NULL
        OR month_num IS NULL
        OR quarter_num IS NULL
        OR period_month IS NULL
        OR period_month NOT RLIKE '^[0-9]{4}-(0[1-9]|1[0-2])$'
    ) = 0,
    'malformed period_month in ledger feed'
)
FROM (
    SELECT DISTINCT
        period_month,
        CAST(substr(period_month, 1, 4) AS INT) AS year_num,
        CAST(substr(period_month, 6, 2) AS INT) AS month_num,
        CAST(ceil(CAST(substr(period_month, 6, 2) AS INT) / 3) AS INT) AS quarter_num
    FROM ow_tp.bronze.commission_ledger_cdw
    WHERE {{p_period_month}} IS NULL OR period_month = {{p_period_month}}
);

MERGE INTO ow_tp.silver.dim_period_cdw d
USING (
    SELECT
        s.*,
        (SELECT coalesce(max(period_key), 0) FROM ow_tp.silver.dim_period_cdw)
            + row_number() OVER (ORDER BY s.period_month) AS period_key
    FROM (
        SELECT DISTINCT
            period_month,
            CAST(substr(period_month, 1, 4) AS INT) AS year_num,
            CAST(substr(period_month, 6, 2) AS INT) AS month_num,
            CAST(ceil(CAST(substr(period_month, 6, 2) AS INT) / 3) AS INT) AS quarter_num
        FROM ow_tp.bronze.commission_ledger_cdw
        WHERE {{p_period_month}} IS NULL OR period_month = {{p_period_month}}
    ) s
    WHERE NOT EXISTS (
        SELECT 1
        FROM ow_tp.silver.dim_period_cdw d
        WHERE d.period_month = s.period_month
    )
) s
ON d.period_month = s.period_month
WHEN NOT MATCHED THEN INSERT (
    period_key,
    period_month,
    year_num,
    month_num,
    quarter_num,
    loaded_at
)
VALUES (
    s.period_key,
    s.period_month,
    s.year_num,
    s.month_num,
    s.quarter_num,
    current_timestamp()
);
