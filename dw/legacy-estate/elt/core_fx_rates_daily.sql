DELETE FROM core.fx_rates_daily;

INSERT INTO core.fx_rates_daily
    (rate_date, currency_code, rate_to_usd, rate_source, load_ts)
WITH bounds AS (
    SELECT MIN(rate_date) AS first_date, MAX(rate_date) AS last_date
    FROM staging.stg_fx_rates_raw
),
calendar AS (
    SELECT generate_series(first_date, last_date, INTERVAL '1 day')::DATE AS rate_date
    FROM bounds
),
currencies AS (
    SELECT DISTINCT currency_code
    FROM staging.stg_fx_rates_raw
),
grid AS (
    SELECT c.rate_date, x.currency_code
    FROM calendar c
    CROSS JOIN currencies x
)
SELECT g.rate_date,
       g.currency_code,
       NVL(raw.rate_to_usd, (
           SELECT prior.rate_to_usd
           FROM staging.stg_fx_rates_raw prior
           WHERE prior.currency_code = g.currency_code
             AND prior.rate_date <= g.rate_date
           ORDER BY prior.rate_date DESC
           LIMIT 1
       )),
       CASE WHEN raw.rate_to_usd IS NULL THEN 'FORWARD_FILLED'
            ELSE 'SOURCE'
       END,
       NVL(raw.load_ts, TIMESTAMP '2026-01-01 03:50:00')
FROM grid g
LEFT JOIN staging.stg_fx_rates_raw raw
  ON raw.rate_date = g.rate_date
 AND raw.currency_code = g.currency_code;
