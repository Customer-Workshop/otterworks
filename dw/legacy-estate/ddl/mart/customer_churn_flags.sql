-- Churn flags for the lifecycle email campaign.
CREATE TABLE IF NOT EXISTS mart.customer_churn_flags (
    customer_id       BIGINT       NOT NULL ENCODE az64,
    last_order_date   DATE         ENCODE az64,
    days_since_order  INTEGER      ENCODE az64,
    churn_flag        BOOLEAN      ENCODE raw,
    calculated_at     TIMESTAMP    ENCODE az64,
    PRIMARY KEY (customer_id)
)
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (churn_flag, customer_id);
