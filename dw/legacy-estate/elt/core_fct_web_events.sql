DELETE FROM core.fct_web_events;

INSERT INTO core.fct_web_events
    (event_id, session_id, customer_id, event_ts, local_event_ts,
     local_event_date, event_type, page_url, device_type, utm_source,
     event_index, session_event_count, is_conversion, load_ts)
SELECT event_id,
       session_id,
       customer_id,
       event_ts,
       CONVERT_TIMEZONE('UTC', 'America/Los_Angeles', event_ts),
       CONVERT_TIMEZONE('UTC', 'America/Los_Angeles', event_ts)::DATE,
       event_type,
       page_url,
       device_type,
       utm_source,
       ROW_NUMBER() OVER (
           PARTITION BY session_id
           ORDER BY event_ts, event_id
       )::INTEGER,
       COUNT(*) OVER (PARTITION BY session_id)::INTEGER,
       event_type = 'purchase',
       load_ts
FROM staging.stg_web_events_raw;
