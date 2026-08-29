DELETE FROM mart.session_funnel_daily;

INSERT INTO mart.session_funnel_daily
    (local_event_date, sessions, page_view_sessions, add_to_cart_sessions,
     checkout_sessions, purchase_sessions)
WITH session_flags AS (
    SELECT CONVERT_TIMEZONE('UTC', 'America/Los_Angeles', event_ts)::DATE
               AS local_event_date,
           session_id,
           MAX((event_type = 'page_view')::INTEGER) AS has_page_view,
           MAX((event_type = 'add_to_cart')::INTEGER) AS has_add_to_cart,
           MAX((event_type = 'checkout_start')::INTEGER) AS has_checkout,
           MAX((event_type = 'purchase')::INTEGER) AS has_purchase
    FROM staging.stg_web_events_raw
    GROUP BY CONVERT_TIMEZONE('UTC', 'America/Los_Angeles', event_ts)::DATE,
             session_id
)
SELECT local_event_date,
       COUNT(*),
       SUM(has_page_view),
       SUM(has_add_to_cart),
       SUM(has_checkout),
       SUM(has_purchase)
FROM session_flags
GROUP BY local_event_date;
