CREATE TABLE IF NOT EXISTS mart.session_funnel_daily (
    local_event_date DATE        NOT NULL ENCODE az64,
    sessions         BIGINT     ENCODE az64,
    page_view_sessions BIGINT   ENCODE az64,
    add_to_cart_sessions BIGINT ENCODE az64,
    checkout_sessions BIGINT    ENCODE az64,
    purchase_sessions BIGINT    ENCODE az64
)
DISTSTYLE ALL
SORTKEY (local_event_date);
