-- Tables the orders service owns, plus read-only reference copies of the catalog data it prices against.
-- Runtime data crosses service boundaries only by business reference (order_ref, hold_ref, ticket_code);
-- catalog ids (performance_id, price_zone_id, seat_inventory_id) are shared opaque identifiers seeded
-- identically in every service from the same synthetic seed.

-- reference copies (seeded by V2, never written at runtime except promo_codes.used_count)
CREATE TABLE venues (
  id          BIGSERIAL PRIMARY KEY,
  code        VARCHAR(16) NOT NULL UNIQUE,
  name        VARCHAR(120) NOT NULL,
  city        VARCHAR(80) NOT NULL,
  timezone    VARCHAR(40) NOT NULL DEFAULT 'UTC',
  capacity    INT NOT NULL
);

CREATE TABLE price_zones (
  id          BIGSERIAL PRIMARY KEY,
  venue_id    BIGINT NOT NULL REFERENCES venues(id),
  code        VARCHAR(8) NOT NULL,
  name        VARCHAR(40) NOT NULL,
  UNIQUE (venue_id, code)
);

CREATE TABLE events (
  id            BIGSERIAL PRIMARY KEY,
  code          VARCHAR(24) NOT NULL UNIQUE,
  title         VARCHAR(160) NOT NULL,
  category      VARCHAR(40) NOT NULL,
  promoter_id   BIGINT NOT NULL,
  description   TEXT,
  on_sale_at    TIMESTAMP NOT NULL,
  status        VARCHAR(16) NOT NULL DEFAULT 'ON_SALE'
);

CREATE TABLE performances (
  id            BIGSERIAL PRIMARY KEY,
  event_id      BIGINT NOT NULL REFERENCES events(id),
  venue_id      BIGINT NOT NULL REFERENCES venues(id),
  starts_at     TIMESTAMP NOT NULL,
  doors_at      TIMESTAMP NOT NULL,
  max_per_order INT NOT NULL DEFAULT 8,
  status        VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED'
);

CREATE TABLE performance_price_levels (
  id               BIGSERIAL PRIMARY KEY,
  performance_id   BIGINT NOT NULL REFERENCES performances(id),
  price_zone_id    BIGINT NOT NULL REFERENCES price_zones(id),
  face_value_cents BIGINT NOT NULL,
  demand_factor_bp INT NOT NULL DEFAULT 10000,
  UNIQUE (performance_id, price_zone_id)
);

CREATE TABLE promo_codes (
  id            BIGSERIAL PRIMARY KEY,
  code          VARCHAR(24) NOT NULL UNIQUE,
  percent_off   INT NOT NULL,
  event_id      BIGINT REFERENCES events(id),
  max_uses      INT NOT NULL DEFAULT 1000,
  used_count    INT NOT NULL DEFAULT 0,
  valid_until   TIMESTAMP NOT NULL
);

CREATE TABLE delivery_methods (
  id          BIGSERIAL PRIMARY KEY,
  code        VARCHAR(16) NOT NULL UNIQUE,
  name        VARCHAR(60) NOT NULL,
  fee_cents   BIGINT NOT NULL DEFAULT 0
);

-- owned tables
-- status: PENDING_PAYMENT, CONFIRMED, PAYMENT_FAILED, PAYMENT_TIMEOUT, CANCELLED
-- payment_outcome: PENDING, APPROVED, DECLINED, TIMEOUT, HOLD_EXPIRED
CREATE TABLE orders (
  id                 BIGSERIAL PRIMARY KEY,
  order_ref          VARCHAR(24) NOT NULL UNIQUE,
  client_ref         VARCHAR(120) UNIQUE,
  customer_email     VARCHAR(160) NOT NULL,
  performance_id     BIGINT NOT NULL REFERENCES performances(id),
  hold_ref           VARCHAR(24) NOT NULL,
  hold_expires_at    TIMESTAMPTZ,
  delivery_method_id BIGINT REFERENCES delivery_methods(id),
  promo_code_id      BIGINT REFERENCES promo_codes(id),
  status             VARCHAR(20) NOT NULL,
  payment_outcome    VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  subtotal_cents     BIGINT NOT NULL,
  fees_cents         BIGINT NOT NULL,
  total_cents        BIGINT NOT NULL,
  channel            VARCHAR(12) NOT NULL DEFAULT 'WEB',
  card_last4         CHAR(4),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_orders_perf_status ON orders (performance_id, status);
CREATE INDEX ix_orders_created ON orders (created_at);
CREATE INDEX ix_orders_hold_ref ON orders (hold_ref);

CREATE TABLE order_items (
  id                BIGSERIAL PRIMARY KEY,
  order_id          BIGINT NOT NULL REFERENCES orders(id),
  seat_inventory_id BIGINT NOT NULL,
  price_zone_id     BIGINT NOT NULL,
  price_cents       BIGINT NOT NULL,
  section           VARCHAR(16) NOT NULL,
  row_label         VARCHAR(8) NOT NULL,
  seat_number       INT NOT NULL,
  zone_code         VARCHAR(8) NOT NULL,
  zone_name         VARCHAR(40) NOT NULL,
  ticket_code       VARCHAR(24)
);
CREATE INDEX ix_order_items_order ON order_items (order_id);

CREATE TABLE order_fees (
  id           BIGSERIAL PRIMARY KEY,
  order_id     BIGINT NOT NULL REFERENCES orders(id),
  fee_type     VARCHAR(24) NOT NULL,     -- SERVICE, FACILITY, DELIVERY
  amount_cents BIGINT NOT NULL
);
CREATE INDEX ix_order_fees_order ON order_fees (order_id);

-- transactional outbox; the relay publishes rows in id order and stamps published_at
CREATE TABLE outbox (
  id            BIGSERIAL PRIMARY KEY,
  aggregate_ref TEXT NOT NULL,
  event_name    TEXT NOT NULL,
  key           TEXT NOT NULL,
  payload       JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at  TIMESTAMPTZ
);
CREATE INDEX ix_outbox_unpublished ON outbox (id) WHERE published_at IS NULL;
