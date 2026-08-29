-- PostgreSQL implementations of the Redshift scalar/date functions used by
-- the legacy estate. These functions are installed once in analytics_dw.

CREATE OR REPLACE FUNCTION getdate()
RETURNS TIMESTAMP
LANGUAGE SQL
STABLE
AS $$ SELECT CURRENT_TIMESTAMP::TIMESTAMP $$;

CREATE OR REPLACE FUNCTION dateadd(
    part TEXT,
    amount BIGINT,
    value TIMESTAMP
)
RETURNS TIMESTAMP
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT CASE lower(part)
        WHEN 'second' THEN value + amount * INTERVAL '1 second'
        WHEN 'minute' THEN value + amount * INTERVAL '1 minute'
        WHEN 'hour'   THEN value + amount * INTERVAL '1 hour'
        WHEN 'day'    THEN value + amount * INTERVAL '1 day'
        WHEN 'week'   THEN value + amount * INTERVAL '1 week'
        WHEN 'month'  THEN value + amount * INTERVAL '1 month'
        WHEN 'quarter' THEN value + amount * INTERVAL '3 months'
        WHEN 'year'   THEN value + amount * INTERVAL '1 year'
        ELSE NULL
    END
$$;

CREATE OR REPLACE FUNCTION datediff(
    part TEXT,
    start_value TIMESTAMP,
    end_value TIMESTAMP
)
RETURNS BIGINT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT CASE lower(part)
        WHEN 'second' THEN EXTRACT(EPOCH FROM (end_value - start_value))::BIGINT
        WHEN 'minute' THEN (EXTRACT(EPOCH FROM (end_value - start_value)) / 60)::BIGINT
        WHEN 'hour'   THEN (EXTRACT(EPOCH FROM (end_value - start_value)) / 3600)::BIGINT
        WHEN 'day'    THEN (end_value::DATE - start_value::DATE)::BIGINT
        WHEN 'week'   THEN ((end_value::DATE - start_value::DATE) / 7)::BIGINT
        WHEN 'month'  THEN ((EXTRACT(YEAR FROM end_value) - EXTRACT(YEAR FROM start_value)) * 12
                            + EXTRACT(MONTH FROM end_value) - EXTRACT(MONTH FROM start_value))::BIGINT
        WHEN 'quarter' THEN (((EXTRACT(YEAR FROM end_value) - EXTRACT(YEAR FROM start_value)) * 12
                              + EXTRACT(MONTH FROM end_value) - EXTRACT(MONTH FROM start_value)) / 3)::BIGINT
        WHEN 'year'   THEN (EXTRACT(YEAR FROM end_value) - EXTRACT(YEAR FROM start_value))::BIGINT
        ELSE NULL
    END
$$;

CREATE OR REPLACE FUNCTION convert_timezone(
    source_zone TEXT,
    target_zone TEXT,
    value TIMESTAMP
)
RETURNS TIMESTAMP
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT value AT TIME ZONE source_zone AT TIME ZONE target_zone
$$;

CREATE OR REPLACE FUNCTION nvl(
    first_value ANYCOMPATIBLE,
    second_value ANYCOMPATIBLE
)
RETURNS ANYCOMPATIBLE
LANGUAGE SQL
IMMUTABLE
AS $$ SELECT COALESCE(first_value, second_value) $$;
