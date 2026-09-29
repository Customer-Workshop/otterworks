-- BoxOffice schema v4.7 (single shared schema, all modules read and write it)
-- Owned by: nobody in particular. Every module joins across it.

CREATE TABLE IF NOT EXISTS promoters (
  id            BIGSERIAL PRIMARY KEY,
  code          VARCHAR(16) NOT NULL UNIQUE,
  name          VARCHAR(120) NOT NULL,
  commission_bp INT NOT NULL DEFAULT 1000,          -- basis points kept by the house
  payout_iban   VARCHAR(40),
  created_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS venues (
  id          BIGSERIAL PRIMARY KEY,
  code        VARCHAR(16) NOT NULL UNIQUE,
  name        VARCHAR(120) NOT NULL,
  city        VARCHAR(80) NOT NULL,
  timezone    VARCHAR(40) NOT NULL DEFAULT 'UTC',
  capacity    INT NOT NULL
);

CREATE TABLE IF NOT EXISTS venue_sections (
  id          BIGSERIAL PRIMARY KEY,
  venue_id    BIGINT NOT NULL REFERENCES venues(id),
  code        VARCHAR(16) NOT NULL,
  name        VARCHAR(80) NOT NULL,
  row_count   INT NOT NULL,
  seats_per_row INT NOT NULL,
  UNIQUE (venue_id, code)
);

CREATE TABLE IF NOT EXISTS price_zones (
  id          BIGSERIAL PRIMARY KEY,
  venue_id    BIGINT NOT NULL REFERENCES venues(id),
  code        VARCHAR(8) NOT NULL,
  name        VARCHAR(40) NOT NULL,
  UNIQUE (venue_id, code)
);

CREATE TABLE IF NOT EXISTS seats (
  id            BIGSERIAL PRIMARY KEY,
  section_id    BIGINT NOT NULL REFERENCES venue_sections(id),
  price_zone_id BIGINT NOT NULL REFERENCES price_zones(id),
  row_label     VARCHAR(4) NOT NULL,
  seat_number   INT NOT NULL,
  accessible    BOOLEAN NOT NULL DEFAULT false,
  UNIQUE (section_id, row_label, seat_number)
);

CREATE TABLE IF NOT EXISTS performers (
  id          BIGSERIAL PRIMARY KEY,
  name        VARCHAR(120) NOT NULL,
  genre       VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id            BIGSERIAL PRIMARY KEY,
  code          VARCHAR(24) NOT NULL UNIQUE,
  title         VARCHAR(160) NOT NULL,
  category      VARCHAR(40) NOT NULL,
  promoter_id   BIGINT NOT NULL REFERENCES promoters(id),
  description   TEXT,
  on_sale_at    TIMESTAMP NOT NULL,
  status        VARCHAR(16) NOT NULL DEFAULT 'ON_SALE'
);

CREATE TABLE IF NOT EXISTS event_performers (
  event_id      BIGINT NOT NULL REFERENCES events(id),
  performer_id  BIGINT NOT NULL REFERENCES performers(id),
  billing_order INT NOT NULL DEFAULT 1,
  PRIMARY KEY (event_id, performer_id)
);

CREATE TABLE IF NOT EXISTS performances (
  id            BIGSERIAL PRIMARY KEY,
  event_id      BIGINT NOT NULL REFERENCES events(id),
  venue_id      BIGINT NOT NULL REFERENCES venues(id),
  starts_at     TIMESTAMP NOT NULL,
  doors_at      TIMESTAMP NOT NULL,
  max_per_order INT NOT NULL DEFAULT 8,
  status        VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED'
);

CREATE TABLE IF NOT EXISTS performance_price_levels (
  id              BIGSERIAL PRIMARY KEY,
  performance_id  BIGINT NOT NULL REFERENCES performances(id),
  price_zone_id   BIGINT NOT NULL REFERENCES price_zones(id),
  face_value_cents BIGINT NOT NULL,
  demand_factor_bp INT NOT NULL DEFAULT 10000,
  UNIQUE (performance_id, price_zone_id)
);

-- seat state per performance: AVAILABLE, HELD, SOLD, KILLED
CREATE TABLE IF NOT EXISTS seat_inventory (
  id              BIGSERIAL PRIMARY KEY,
  performance_id  BIGINT NOT NULL REFERENCES performances(id),
  seat_id         BIGINT NOT NULL REFERENCES seats(id),
  status          VARCHAR(12) NOT NULL DEFAULT 'AVAILABLE',
  hold_id         BIGINT,
  order_id        BIGINT,
  updated_at      TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (performance_id, seat_id)
);
CREATE INDEX IF NOT EXISTS ix_seat_inventory_perf_status ON seat_inventory (performance_id, status);

CREATE TABLE IF NOT EXISTS customers (
  id          BIGSERIAL PRIMARY KEY,
  email       VARCHAR(160) NOT NULL UNIQUE,
  full_name   VARCHAR(120),
  phone       VARCHAR(32),
  created_at  TIMESTAMP NOT NULL DEFAULT now(),
  marketing_opt_in BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS customer_addresses (
  id          BIGSERIAL PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES customers(id),
  line1       VARCHAR(120) NOT NULL,
  city        VARCHAR(80) NOT NULL,
  postal_code VARCHAR(16) NOT NULL,
  country     CHAR(2) NOT NULL DEFAULT 'US'
);

CREATE TABLE IF NOT EXISTS seat_holds (
  id              BIGSERIAL PRIMARY KEY,
  hold_ref        VARCHAR(24) NOT NULL UNIQUE,
  performance_id  BIGINT NOT NULL REFERENCES performances(id),
  customer_id     BIGINT REFERENCES customers(id),
  status          VARCHAR(12) NOT NULL DEFAULT 'ACTIVE',    -- ACTIVE, CONVERTED, EXPIRED, RELEASED
  created_at      TIMESTAMP NOT NULL DEFAULT now(),
  expires_at      TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_seat_holds_status_exp ON seat_holds (status, expires_at);

CREATE TABLE IF NOT EXISTS seat_hold_items (
  hold_id     BIGINT NOT NULL REFERENCES seat_holds(id),
  seat_inventory_id BIGINT NOT NULL REFERENCES seat_inventory(id),
  PRIMARY KEY (hold_id, seat_inventory_id)
);

CREATE TABLE IF NOT EXISTS carts (
  id          BIGSERIAL PRIMARY KEY,
  session_key VARCHAR(64) NOT NULL UNIQUE,
  customer_id BIGINT REFERENCES customers(id),
  hold_id     BIGINT REFERENCES seat_holds(id),
  created_at  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cart_items (
  id          BIGSERIAL PRIMARY KEY,
  cart_id     BIGINT NOT NULL REFERENCES carts(id),
  seat_inventory_id BIGINT NOT NULL REFERENCES seat_inventory(id),
  price_cents BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS promo_codes (
  id            BIGSERIAL PRIMARY KEY,
  code          VARCHAR(24) NOT NULL UNIQUE,
  percent_off   INT NOT NULL,
  event_id      BIGINT REFERENCES events(id),
  max_uses      INT NOT NULL DEFAULT 1000,
  used_count    INT NOT NULL DEFAULT 0,
  valid_until   TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_methods (
  id          BIGSERIAL PRIMARY KEY,
  code        VARCHAR(16) NOT NULL UNIQUE,
  name        VARCHAR(60) NOT NULL,
  fee_cents   BIGINT NOT NULL DEFAULT 0
);

-- status: PENDING_PAYMENT, CONFIRMED, PAYMENT_FAILED, PAYMENT_TIMEOUT, CANCELLED, REFUNDED
CREATE TABLE IF NOT EXISTS orders (
  id              BIGSERIAL PRIMARY KEY,
  order_ref       VARCHAR(24) NOT NULL UNIQUE,
  customer_id     BIGINT NOT NULL REFERENCES customers(id),
  performance_id  BIGINT NOT NULL REFERENCES performances(id),
  hold_id         BIGINT REFERENCES seat_holds(id),
  delivery_method_id BIGINT REFERENCES delivery_methods(id),
  promo_code_id   BIGINT REFERENCES promo_codes(id),
  status          VARCHAR(20) NOT NULL,
  subtotal_cents  BIGINT NOT NULL,
  fees_cents      BIGINT NOT NULL,
  total_cents     BIGINT NOT NULL,
  channel         VARCHAR(12) NOT NULL DEFAULT 'WEB',
  created_at      TIMESTAMP NOT NULL DEFAULT now(),
  updated_at      TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_orders_perf_status ON orders (performance_id, status);
CREATE INDEX IF NOT EXISTS ix_orders_created ON orders (created_at);

CREATE TABLE IF NOT EXISTS order_items (
  id              BIGSERIAL PRIMARY KEY,
  order_id        BIGINT NOT NULL REFERENCES orders(id),
  seat_inventory_id BIGINT NOT NULL REFERENCES seat_inventory(id),
  price_zone_id   BIGINT NOT NULL REFERENCES price_zones(id),
  price_cents     BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_fees (
  id          BIGSERIAL PRIMARY KEY,
  order_id    BIGINT NOT NULL REFERENCES orders(id),
  fee_type    VARCHAR(24) NOT NULL,     -- SERVICE, FACILITY, DELIVERY
  amount_cents BIGINT NOT NULL
);

-- status: AUTHORIZED, CAPTURED, DECLINED, TIMEOUT, REFUNDED
CREATE TABLE IF NOT EXISTS payments (
  id              BIGSERIAL PRIMARY KEY,
  order_id        BIGINT NOT NULL REFERENCES orders(id),
  amount_cents    BIGINT NOT NULL,
  currency        CHAR(3) NOT NULL DEFAULT 'USD',
  status          VARCHAR(16) NOT NULL,
  gateway_ref     VARCHAR(40),
  card_last4      CHAR(4),
  created_at      TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_payments_order ON payments (order_id);

CREATE TABLE IF NOT EXISTS payment_attempts (
  id              BIGSERIAL PRIMARY KEY,
  order_id        BIGINT NOT NULL REFERENCES orders(id),
  attempt_no      INT NOT NULL,
  outcome         VARCHAR(16) NOT NULL,
  latency_ms      INT NOT NULL,
  created_at      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refunds (
  id              BIGSERIAL PRIMARY KEY,
  payment_id      BIGINT NOT NULL REFERENCES payments(id),
  amount_cents    BIGINT NOT NULL,
  reason          VARCHAR(80) NOT NULL,
  created_at      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tickets (
  id              BIGSERIAL PRIMARY KEY,
  ticket_code     VARCHAR(32) NOT NULL UNIQUE,
  order_id        BIGINT NOT NULL REFERENCES orders(id),
  seat_inventory_id BIGINT NOT NULL REFERENCES seat_inventory(id),
  barcode         VARCHAR(64) NOT NULL,
  issued_at       TIMESTAMP NOT NULL DEFAULT now(),
  scanned_at      TIMESTAMP
);

-- written in the purchase transaction, mailed later by an ops cron
CREATE TABLE IF NOT EXISTS confirmations (
  id              BIGSERIAL PRIMARY KEY,
  order_id        BIGINT NOT NULL REFERENCES orders(id),
  channel         VARCHAR(8) NOT NULL DEFAULT 'EMAIL',
  recipient       VARCHAR(160) NOT NULL,
  subject         VARCHAR(200) NOT NULL,
  body            TEXT NOT NULL,
  sent_at         TIMESTAMP,
  created_at      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settlement_batches (
  id              BIGSERIAL PRIMARY KEY,
  business_date   DATE NOT NULL,
  promoter_id     BIGINT NOT NULL REFERENCES promoters(id),
  gross_cents     BIGINT NOT NULL,
  fees_cents      BIGINT NOT NULL,
  refunds_cents   BIGINT NOT NULL,
  net_payout_cents BIGINT NOT NULL,
  order_count     INT NOT NULL,
  status          VARCHAR(12) NOT NULL DEFAULT 'OPEN',
  created_at      TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (business_date, promoter_id)
);

CREATE TABLE IF NOT EXISTS settlement_lines (
  id              BIGSERIAL PRIMARY KEY,
  batch_id        BIGINT NOT NULL REFERENCES settlement_batches(id),
  performance_id  BIGINT NOT NULL REFERENCES performances(id),
  tickets_sold    INT NOT NULL,
  gross_cents     BIGINT NOT NULL,
  house_commission_cents BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          BIGSERIAL PRIMARY KEY,
  module      VARCHAR(24) NOT NULL,
  action      VARCHAR(40) NOT NULL,
  entity_ref  VARCHAR(40),
  detail      TEXT,
  created_at  TIMESTAMP NOT NULL DEFAULT now()
);
