DELETE FROM core.dim_date;

INSERT INTO core.dim_date
    (date_key, calendar_year, calendar_month, month_name, calendar_day,
     day_of_week, day_name, week_of_year, quarter_num, fiscal_year,
     fiscal_quarter, is_weekend)
SELECT date_key,
       EXTRACT(YEAR FROM date_key)::INTEGER,
       EXTRACT(MONTH FROM date_key)::INTEGER,
       TO_CHAR(date_key, 'Month'),
       EXTRACT(DAY FROM date_key)::INTEGER,
       EXTRACT(DOW FROM date_key)::INTEGER,
       TO_CHAR(date_key, 'Day'),
       EXTRACT(WEEK FROM date_key)::INTEGER,
       EXTRACT(QUARTER FROM date_key)::INTEGER,
       CASE WHEN EXTRACT(MONTH FROM date_key) >= 4
            THEN EXTRACT(YEAR FROM date_key)::INTEGER
            ELSE EXTRACT(YEAR FROM date_key)::INTEGER - 1
       END,
       CASE
           WHEN EXTRACT(MONTH FROM date_key) BETWEEN 4 AND 6 THEN 1
           WHEN EXTRACT(MONTH FROM date_key) BETWEEN 7 AND 9 THEN 2
           WHEN EXTRACT(MONTH FROM date_key) BETWEEN 10 AND 12 THEN 3
           ELSE 4
       END,
       EXTRACT(DOW FROM date_key) IN (0, 6)
FROM (
    SELECT DATEADD('day', n, TIMESTAMP '2022-01-01 00:00:00')::DATE AS date_key
    FROM generate_series(0, DATEDIFF('day',
                                      TIMESTAMP '2022-01-01 00:00:00',
                                      TIMESTAMP '2026-12-31 00:00:00')) AS g(n)
) calendar;
