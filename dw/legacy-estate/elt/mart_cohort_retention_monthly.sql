DELETE FROM mart.cohort_retention_monthly;

INSERT INTO mart.cohort_retention_monthly
    (cohort_month, activity_month, cohort_size, active_customers,
     retention_pct)
WITH cohorts AS (
    SELECT customer_id,
           DATE_TRUNC('month', signup_ts)::DATE AS cohort_month
    FROM staging.stg_customers_raw
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM cohorts
    GROUP BY cohort_month
),
activity AS (
    SELECT DISTINCT customer_id,
           DATE_TRUNC('month', event_ts)::DATE AS activity_month
    FROM staging.stg_web_events_raw
    WHERE customer_id IS NOT NULL
),
retained AS (
    SELECT c.cohort_month,
           a.activity_month,
           COUNT(DISTINCT a.customer_id) AS active_customers
    FROM cohorts c
    JOIN activity a ON a.customer_id = c.customer_id
    GROUP BY c.cohort_month, a.activity_month
)
SELECT r.cohort_month,
       r.activity_month,
       s.cohort_size,
       r.active_customers,
       ROUND(r.active_customers::NUMERIC / NULLIF(s.cohort_size, 0), 4)
FROM retained r
JOIN cohort_sizes s ON s.cohort_month = r.cohort_month;
