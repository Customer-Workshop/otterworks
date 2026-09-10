CREATE SCHEMA IF NOT EXISTS webhook;
CREATE TABLE IF NOT EXISTS webhook.subscriptions (
  id uuid PRIMARY KEY, owner_id text NOT NULL, target_url text NOT NULL,
  event_types text[] NOT NULL, description text NOT NULL DEFAULT '', secret text NOT NULL,
  active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook.deliveries (
  id uuid PRIMARY KEY, subscription_id uuid NOT NULL REFERENCES webhook.subscriptions(id) ON DELETE CASCADE,
  event_type text NOT NULL, payload jsonb NOT NULL, status text NOT NULL CHECK (status IN ('pending','delivered','failed')),
  attempts int NOT NULL DEFAULT 0, max_attempts int NOT NULL, last_response_code int NULL, last_error text NULL,
  next_attempt_at timestamptz NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, delivered_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS deliveries_subscription_created_idx ON webhook.deliveries(subscription_id, created_at DESC);
CREATE INDEX IF NOT EXISTS deliveries_due_idx ON webhook.deliveries(status, next_attempt_at);
CREATE TABLE IF NOT EXISTS webhook.delivery_attempts (
  id uuid PRIMARY KEY, delivery_id uuid NOT NULL REFERENCES webhook.deliveries(id) ON DELETE CASCADE,
  attempt int NOT NULL, response_code int NULL, error text NULL, duration_ms int NOT NULL, attempted_at timestamptz NOT NULL
);
