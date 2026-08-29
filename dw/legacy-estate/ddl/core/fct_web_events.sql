-- Sessionised clickstream fact.
CREATE TABLE IF NOT EXISTS core.fct_web_events (
    event_id          BIGINT       NOT NULL ENCODE az64,
    session_id        BIGINT       NOT NULL ENCODE az64,
    customer_id       BIGINT       ENCODE az64,
    event_ts          TIMESTAMP    ENCODE az64,
    local_event_ts    TIMESTAMP    ENCODE az64,
    local_event_date  DATE         ENCODE az64,
    event_type        VARCHAR(24)  ENCODE bytedict,
    page_url          VARCHAR(200) ENCODE lzo,
    device_type       VARCHAR(16)  ENCODE bytedict,
    utm_source        VARCHAR(32)  ENCODE bytedict,
    event_index       INTEGER      ENCODE az64,
    session_event_count INTEGER    ENCODE az64,
    is_conversion     BOOLEAN      ENCODE raw,
    load_ts           TIMESTAMP    ENCODE az64,
    PRIMARY KEY (event_id)
)
DISTSTYLE EVEN
COMPOUND SORTKEY (local_event_date, session_id, event_ts);
