-- =====================================================================
-- analytics_dw landing-zone seed (deterministic)
-- =====================================================================
-- Populates the seven staging.* landing tables that the legacy ELT reads.
-- Everything is derived arithmetically from the row index, so the same
-- statements produce byte-identical data on every run and on every engine
-- that supports generate_series + BIGINT arithmetic (Postgres, DuckDB).
--
-- Derivation macro (inlined by hand because CREATE FUNCTION / CREATE MACRO
-- are not portable): for row index i and stream k,
--     r(i,k) = (i * 1103515245 + k * 2654435761 + 12345) % 2147483647
-- Only integer arithmetic is used to pick values, so no RNG state, no
-- ordering dependency, and no locale/collation dependency exists.
--
-- Volumes (fixed on purpose - the equivalence gates key off these counts):
--   stg_customers_raw        60,000
--   stg_products_raw          8,000
--   stg_orders_raw          400,000 + 1,201 re-delivered duplicates
--   stg_order_items_raw   ~1,080,000
--   stg_web_events_raw    2,000,000
--   stg_returns_raw          ~27,000
--   stg_fx_rates_raw          4,384
-- =====================================================================

DELETE FROM staging.stg_fx_rates_raw;
DELETE FROM staging.stg_returns_raw;
DELETE FROM staging.stg_web_events_raw;
DELETE FROM staging.stg_order_items_raw;
DELETE FROM staging.stg_orders_raw;
DELETE FROM staging.stg_products_raw;
DELETE FROM staging.stg_customers_raw;

-- ---------------------------------------------------------------------
-- customers: 60,000 rows, signup spread over 2022-01-01 .. 2025-12-31
-- ---------------------------------------------------------------------
INSERT INTO staging.stg_customers_raw
    (customer_id, customer_name, email, signup_ts, country_code, city,
     segment, marketing_opt_in, source_system, load_ts)
WITH base AS (
    SELECT i,
           (CAST(i AS BIGINT) * 1103515245 + 1 * 2654435761 + 12345) % 2147483647 AS r1,
           (CAST(i AS BIGINT) * 1103515245 + 2 * 2654435761 + 12345) % 2147483647 AS r2,
           (CAST(i AS BIGINT) * 1103515245 + 3 * 2654435761 + 12345) % 2147483647 AS r3,
           (CAST(i AS BIGINT) * 1103515245 + 4 * 2654435761 + 12345) % 2147483647 AS r4
    FROM generate_series(1, 60000) AS g(i)
)
SELECT i,
       'Customer ' || CAST(i AS VARCHAR),
       'user' || CAST(i AS VARCHAR) || '@example.com',
       TIMESTAMP '2022-01-01 00:00:00' + ((r1 % 126144000) * INTERVAL '1 second'),
       CASE r2 % 6 WHEN 0 THEN 'US' WHEN 1 THEN 'US' WHEN 2 THEN 'GB'
                   WHEN 3 THEN 'DE' WHEN 4 THEN 'CA' ELSE 'FR' END,
       CASE r3 % 8 WHEN 0 THEN 'Seattle'  WHEN 1 THEN 'Austin'
                   WHEN 2 THEN 'London'   WHEN 3 THEN 'Berlin'
                   WHEN 4 THEN 'Toronto'  WHEN 5 THEN 'Paris'
                   WHEN 6 THEN 'Chicago'  ELSE 'Denver' END,
       -- inconsistent casing in the CRM feed is intentional (real wart)
       CASE r4 % 5 WHEN 0 THEN 'ENTERPRISE' WHEN 1 THEN 'enterprise'
                   WHEN 2 THEN 'SMB'        WHEN 3 THEN 'CONSUMER'
                   ELSE 'consumer' END,
       (r2 % 3) > 0,
       'SFDC_EXPORT',
       TIMESTAMP '2026-01-01 03:15:00'
FROM base;

-- ---------------------------------------------------------------------
-- products: 8,000 rows
-- ---------------------------------------------------------------------
INSERT INTO staging.stg_products_raw
    (product_id, product_name, category, subcategory, brand,
     unit_cost, list_price, is_active, supplier_id, load_ts)
WITH base AS (
    SELECT i,
           (CAST(i AS BIGINT) * 1103515245 + 11 * 2654435761 + 12345) % 2147483647 AS r1,
           (CAST(i AS BIGINT) * 1103515245 + 12 * 2654435761 + 12345) % 2147483647 AS r2,
           (CAST(i AS BIGINT) * 1103515245 + 13 * 2654435761 + 12345) % 2147483647 AS r3
    FROM generate_series(1, 8000) AS g(i)
),
priced AS (
    SELECT i, r1, r2, r3,
           ROUND(((r1 % 24000) + 500) / 100.0, 2) AS unit_cost
    FROM base
)
SELECT i,
       'Product ' || CAST(i AS VARCHAR),
       CASE i % 6 WHEN 0 THEN 'Apparel'   WHEN 1 THEN 'Electronics'
                  WHEN 2 THEN 'Home'      WHEN 3 THEN 'Grocery'
                  WHEN 4 THEN 'Outdoors'  ELSE 'Beauty' END,
       'Subcat ' || CAST(i % 24 AS VARCHAR),
       'Brand ' || CAST(i % 40 AS VARCHAR),
       unit_cost,
       ROUND(unit_cost * 1.45, 2),
       (r2 % 20) > 0,
       CAST((r3 % 120) + 1 AS INTEGER),
       TIMESTAMP '2026-01-01 03:20:00'
FROM priced;

-- ---------------------------------------------------------------------
-- orders: 400,000 rows over 2023-01-01 .. 2025-12-31 (1096 days)
-- ---------------------------------------------------------------------
INSERT INTO staging.stg_orders_raw
    (order_id, customer_id, order_ts, channel, store_id, currency_code,
     order_status, gross_amount, discount_amount, shipping_amount,
     tax_amount, promo_code, source_file, load_ts)
WITH base AS (
    SELECT i,
           (CAST(i AS BIGINT) * 1103515245 + 21 * 2654435761 + 12345) % 2147483647 AS r1,
           (CAST(i AS BIGINT) * 1103515245 + 22 * 2654435761 + 12345) % 2147483647 AS r2,
           (CAST(i AS BIGINT) * 1103515245 + 23 * 2654435761 + 12345) % 2147483647 AS r3,
           (CAST(i AS BIGINT) * 1103515245 + 24 * 2654435761 + 12345) % 2147483647 AS r4,
           (CAST(i AS BIGINT) * 1103515245 + 25 * 2654435761 + 12345) % 2147483647 AS r5
    FROM generate_series(1, 400000) AS g(i)
),
amounts AS (
    SELECT i, r1, r2, r3, r4, r5,
           TIMESTAMP '2023-01-01 00:00:00' + ((r1 % 94694400) * INTERVAL '1 second') AS order_ts,
           ROUND(((r2 % 240000) + 1500) / 100.0, 2) AS gross_amount
    FROM base
)
SELECT i,
       (r3 % 60000) + 1,
       order_ts,
       CASE r4 % 5 WHEN 0 THEN 'STORE' WHEN 1 THEN 'WEB' WHEN 2 THEN 'WEB'
                   WHEN 3 THEN 'MOBILE' ELSE 'CALL_CENTER' END,
       CAST(CASE WHEN r4 % 5 = 0 THEN (r5 % 180) + 1 ELSE 0 END AS INTEGER),
       CASE WHEN r5 % 10 < 7 THEN 'USD' WHEN r5 % 10 = 7 THEN 'EUR'
            WHEN r5 % 10 = 8 THEN 'GBP' ELSE 'CAD' END,
       CASE r2 % 20 WHEN 0 THEN 'CANCELLED' WHEN 1 THEN 'PENDING' ELSE 'COMPLETED' END,
       gross_amount,
       ROUND(gross_amount * ((r3 % 15) / 100.0), 2),
       ROUND(((r4 % 1800) + 200) / 100.0, 2),
       ROUND(gross_amount * 0.0825, 2),
       CASE WHEN r5 % 7 = 0 THEN 'PROMO' || CAST(r5 % 40 AS VARCHAR) ELSE NULL END,
       'orders_' || CAST(CAST(order_ts AS DATE) AS VARCHAR) || '.csv',
       TIMESTAMP '2026-01-01 03:30:00'
FROM amounts;

-- The 2024-03-17 OMS re-delivery: the retry file was appended instead of
-- replacing the original slice, so these order_ids appear twice in the
-- landing table. core.fct_orders de-duplicates; not every downstream asset
-- remembers to.
INSERT INTO staging.stg_orders_raw
    (order_id, customer_id, order_ts, channel, store_id, currency_code,
     order_status, gross_amount, discount_amount, shipping_amount,
     tax_amount, promo_code, source_file, load_ts)
SELECT order_id, customer_id, order_ts, channel, store_id, currency_code,
       order_status, gross_amount, discount_amount, shipping_amount,
       tax_amount, promo_code, 'orders_20240317_retry.csv',
       TIMESTAMP '2024-03-17 22:41:00'
FROM staging.stg_orders_raw
WHERE order_id % 333 = 7;

-- ---------------------------------------------------------------------
-- order items: three candidate lines per order, ~10% never delivered
-- ---------------------------------------------------------------------
INSERT INTO staging.stg_order_items_raw
    (order_item_id, order_id, product_id, quantity, unit_price,
     item_discount, line_amount, load_ts)
WITH base AS (
    SELECT i,
           ((i - 1) / 3) + 1 AS order_id,
           (CAST(i AS BIGINT) * 1103515245 + 31 * 2654435761 + 12345) % 2147483647 AS r1,
           (CAST(i AS BIGINT) * 1103515245 + 32 * 2654435761 + 12345) % 2147483647 AS r2,
           (CAST(i AS BIGINT) * 1103515245 + 33 * 2654435761 + 12345) % 2147483647 AS r3
    FROM generate_series(1, 1200000) AS g(i)
),
kept AS (
    SELECT i, order_id, r1, r2, r3, (r1 % 8000) + 1 AS product_id,
           (r2 % 5) + 1 AS quantity
    FROM base
    WHERE r3 % 10 > 0
),
priced AS (
    SELECT k.i, k.order_id, k.product_id, k.quantity, k.r3,
           p.list_price AS unit_price,
           ROUND(p.list_price * k.quantity * ((k.r3 % 12) / 100.0), 2) AS item_discount
    FROM kept k
    JOIN staging.stg_products_raw p ON p.product_id = k.product_id
)
SELECT i, order_id, product_id, CAST(quantity AS INTEGER), unit_price, item_discount,
       ROUND(unit_price * quantity - item_discount, 2),
       TIMESTAMP '2026-01-01 03:35:00'
FROM priced;

-- ---------------------------------------------------------------------
-- web events: 2,000,000 rows, seven events per session
-- ---------------------------------------------------------------------
INSERT INTO staging.stg_web_events_raw
    (event_id, session_id, customer_id, event_ts, event_type, page_url,
     device_type, utm_source, load_ts)
WITH base AS (
    SELECT i,
           ((i - 1) / 7) + 1 AS session_id,
           (CAST(i AS BIGINT) * 1103515245 + 41 * 2654435761 + 12345) % 2147483647 AS r1,
           (CAST(i AS BIGINT) * 1103515245 + 42 * 2654435761 + 12345) % 2147483647 AS r2,
           (CAST(i AS BIGINT) * 1103515245 + 43 * 2654435761 + 12345) % 2147483647 AS r3
    FROM generate_series(1, 2000000) AS g(i)
)
SELECT i,
       session_id,
       CASE WHEN r1 % 5 = 0 THEN NULL ELSE (r1 % 60000) + 1 END,
       TIMESTAMP '2023-01-01 00:00:00' + ((r2 % 94694400) * INTERVAL '1 second'),
       CASE r3 % 6 WHEN 0 THEN 'page_view' WHEN 1 THEN 'page_view'
                   WHEN 2 THEN 'add_to_cart' WHEN 3 THEN 'search'
                   WHEN 4 THEN 'checkout_start' ELSE 'purchase' END,
       '/p/' || CAST((r1 % 8000) + 1 AS VARCHAR),
       CASE r2 % 4 WHEN 0 THEN 'desktop' WHEN 1 THEN 'mobile'
                   WHEN 2 THEN 'mobile'  ELSE 'tablet' END,
       CASE r3 % 5 WHEN 0 THEN 'organic' WHEN 1 THEN 'paid_search'
                   WHEN 2 THEN 'email'   WHEN 3 THEN 'affiliate'
                   ELSE 'direct' END,
       TIMESTAMP '2026-01-01 03:40:00'
FROM base;

-- ---------------------------------------------------------------------
-- returns: every 40th delivered order line comes back
-- ---------------------------------------------------------------------
INSERT INTO staging.stg_returns_raw
    (return_id, order_id, order_item_id, return_ts, reason_code,
     refund_amount, load_ts)
WITH picked AS (
    SELECT oi.order_item_id, oi.order_id, oi.line_amount, o.order_ts,
           (oi.order_item_id * 1103515245 + 51 * 2654435761 + 12345) % 2147483647 AS r1
    FROM staging.stg_order_items_raw oi
    JOIN staging.stg_orders_raw o ON o.order_id = oi.order_id
                                 AND o.source_file NOT LIKE '%_retry.csv'
    WHERE oi.order_item_id % 40 = 3
)
SELECT order_item_id,
       order_id,
       order_item_id,
       order_ts + (((r1 % 30) + 1) * INTERVAL '1 day'),
       CASE r1 % 5 WHEN 0 THEN 'DAMAGED' WHEN 1 THEN 'WRONG_SIZE'
                   WHEN 2 THEN 'NOT_AS_DESCRIBED' WHEN 3 THEN 'LATE'
                   ELSE 'CHANGED_MIND' END,
       line_amount,
       TIMESTAMP '2026-01-01 03:45:00'
FROM picked;

-- ---------------------------------------------------------------------
-- fx rates: 1,096 days x 4 currencies
-- ---------------------------------------------------------------------
INSERT INTO staging.stg_fx_rates_raw
    (rate_date, currency_code, rate_to_usd, load_ts)
WITH days AS (
    SELECT d, DATE '2023-01-01' + (d * INTERVAL '1 day') AS rate_date
    FROM generate_series(0, 1095) AS g(d)
),
ccy AS (
    SELECT 'USD' AS currency_code, 0 AS k UNION ALL
    SELECT 'EUR', 1 UNION ALL
    SELECT 'GBP', 2 UNION ALL
    SELECT 'CAD', 3
)
SELECT CAST(days.rate_date AS DATE),
       ccy.currency_code,
       CASE ccy.currency_code
            WHEN 'USD' THEN 1.000000
            ELSE ROUND((CASE ccy.currency_code WHEN 'EUR' THEN 108000
                                               WHEN 'GBP' THEN 126000
                                               ELSE 74000 END
                        + ((CAST(days.d AS BIGINT) * 1103515245
                            + CAST(ccy.k AS BIGINT) * 2654435761 + 12345) % 2000)) / 100000.0, 6)
       END,
       TIMESTAMP '2026-01-01 03:50:00'
FROM days CROSS JOIN ccy;
