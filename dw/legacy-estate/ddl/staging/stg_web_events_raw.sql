-- Clickstream landing table (highest-volume asset in the estate).
CREATE TABLE IF NOT EXISTS staging.stg_web_events_raw (
    event_id     BIGINT       NOT NULL ENCODE az64,
    session_id   BIGINT       NOT NULL ENCODE az64,
    customer_id  BIGINT       ENCODE az64,
    event_ts     TIMESTAMP    ENCODE az64,
    event_type   VARCHAR(24)  ENCODE bytedict,
    page_url     VARCHAR(200) ENCODE lzo,
    device_type  VARCHAR(16)  ENCODE bytedict,
    utm_source   VARCHAR(32)  ENCODE bytedict,
    load_ts      TIMESTAMP    ENCODE az64
)
DISTSTYLE EVEN
COMPOUND SORTKEY (event_ts, session_id);
