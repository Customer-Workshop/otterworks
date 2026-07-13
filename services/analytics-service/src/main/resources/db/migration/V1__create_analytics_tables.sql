-- Analytics Service: durable event store + daily aggregate rollup.
--
-- This is the "before" state for the analytics lakehouse migration
-- (S3 + Apache Iceberg). The raw event log is the reconciliation source of
-- truth; the daily rollup is a materialized aggregate kept in sync on write.

CREATE TABLE IF NOT EXISTS analytics_events (
    id            BIGSERIAL PRIMARY KEY,
    event_id      VARCHAR(64) NOT NULL UNIQUE,
    event_type    VARCHAR(64) NOT NULL,
    user_id       VARCHAR(128) NOT NULL,
    resource_id   VARCHAR(128) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    metadata      TEXT NOT NULL DEFAULT '{}',
    -- Event instant as epoch-nanoseconds (UTC): round-trips exactly regardless
    -- of database timestamp precision or server time zone.
    occurred_at   BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_user_id ON analytics_events(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_resource_id ON analytics_events(resource_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_event_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_events_occurred_at ON analytics_events(occurred_at);

CREATE TABLE IF NOT EXISTS analytics_daily_metrics (
    event_date  DATE NOT NULL,
    event_type  VARCHAR(64) NOT NULL,
    event_count BIGINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_date, event_type)
);
