CREATE TABLE IF NOT EXISTS mart.cohort_retention_monthly (
    cohort_month       DATE          NOT NULL ENCODE az64,
    activity_month     DATE          NOT NULL ENCODE az64,
    cohort_size        BIGINT        ENCODE az64,
    active_customers   BIGINT        ENCODE az64,
    retention_pct      NUMERIC(9,4)  ENCODE az64
)
DISTSTYLE KEY
DISTKEY (cohort_month)
SORTKEY (cohort_month, activity_month);
