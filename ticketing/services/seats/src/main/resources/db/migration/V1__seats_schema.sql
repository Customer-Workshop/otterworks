-- seats service schema: the inventory context extracted from the BoxOffice monolith
-- (monolith db/schema.sql L93-L104, L124-L139). Owned tables: seat_inventory, seat_holds,
-- seat_hold_items. Reference copies (read-only, seeded by V2 from the same synthetic seed):
-- venues, venue_sections, price_zones, seats, performances.

CREATE TABLE venues (
  id          BIGSERIAL PRIMARY KEY,
  code        VARCHAR(16) NOT NULL UNIQUE,
  name        VARCHAR(120) NOT NULL,
  city        VARCHAR(80) NOT NULL,
  timezone    VARCHAR(40) NOT NULL DEFAULT 'UTC',
  capacity    INT NOT NULL
);

CREATE TABLE venue_sections (
  id          BIGSERIAL PRIMARY KEY,
  venue_id    BIGINT NOT NULL REFERENCES venues(id),
  code        VARCHAR(16) NOT NULL,
  name        VARCHAR(80) NOT NULL,
  row_count   INT NOT NULL,
  seats_per_row INT NOT NULL,
  UNIQUE (venue_id, code)
);

CREATE TABLE price_zones (
  id          BIGSERIAL PRIMARY KEY,
  venue_id    BIGINT NOT NULL REFERENCES venues(id),
  code        VARCHAR(8) NOT NULL,
  name        VARCHAR(40) NOT NULL,
  UNIQUE (venue_id, code)
);

CREATE TABLE seats (
  id            BIGSERIAL PRIMARY KEY,
  section_id    BIGINT NOT NULL REFERENCES venue_sections(id),
  price_zone_id BIGINT NOT NULL REFERENCES price_zones(id),
  row_label     VARCHAR(4) NOT NULL,
  seat_number   INT NOT NULL,
  accessible    BOOLEAN NOT NULL DEFAULT false,
  UNIQUE (section_id, row_label, seat_number)
);

-- events/promoters stay in the monolith; event_id is kept as an opaque reference only.
CREATE TABLE performances (
  id            BIGSERIAL PRIMARY KEY,
  event_id      BIGINT NOT NULL,
  venue_id      BIGINT NOT NULL REFERENCES venues(id),
  starts_at     TIMESTAMP NOT NULL,
  doors_at      TIMESTAMP NOT NULL,
  max_per_order INT NOT NULL DEFAULT 8,
  status        VARCHAR(16) NOT NULL DEFAULT 'SCHEDULED'
);

-- seat state per performance: AVAILABLE, HELD, SOLD, KILLED
CREATE TABLE seat_inventory (
  id              BIGSERIAL PRIMARY KEY,
  performance_id  BIGINT NOT NULL REFERENCES performances(id),
  seat_id         BIGINT NOT NULL REFERENCES seats(id),
  status          VARCHAR(12) NOT NULL DEFAULT 'AVAILABLE',
  hold_id         BIGINT,
  order_ref       VARCHAR(24),
  updated_at      TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (performance_id, seat_id)
);
CREATE INDEX ix_seat_inventory_perf_status ON seat_inventory (performance_id, status);
CREATE INDEX ix_seat_inventory_hold ON seat_inventory (hold_id) WHERE hold_id IS NOT NULL;

CREATE TABLE seat_holds (
  id              BIGSERIAL PRIMARY KEY,
  hold_ref        VARCHAR(24) NOT NULL UNIQUE,
  performance_id  BIGINT NOT NULL REFERENCES performances(id),
  customer_email  VARCHAR(160),
  order_ref       VARCHAR(24),
  status          VARCHAR(12) NOT NULL DEFAULT 'ACTIVE',    -- ACTIVE, CONVERTED, EXPIRED, RELEASED
  created_at      TIMESTAMP NOT NULL DEFAULT now(),
  expires_at      TIMESTAMP NOT NULL
);
CREATE INDEX ix_seat_holds_status_exp ON seat_holds (status, expires_at);
CREATE INDEX ix_seat_holds_order_ref ON seat_holds (order_ref) WHERE order_ref IS NOT NULL;

CREATE TABLE seat_hold_items (
  hold_id     BIGINT NOT NULL REFERENCES seat_holds(id),
  seat_inventory_id BIGINT NOT NULL REFERENCES seat_inventory(id),
  PRIMARY KEY (hold_id, seat_inventory_id)
);

-- Idempotent inbox for events delivered over HTTP (payment-failed, order-confirmed): one row per
-- (event, key); a replay hits the primary key and is acknowledged without being re-applied.
CREATE TABLE inbox (
  event_name  VARCHAR(40) NOT NULL,
  event_key   VARCHAR(64) NOT NULL,
  payload     JSONB NOT NULL,
  received_at TIMESTAMP NOT NULL DEFAULT now(),
  applied     BOOLEAN NOT NULL,
  PRIMARY KEY (event_name, event_key)
);

-- hold-expired records written by the sweep in the same transaction that expires the hold; the
-- Kafka publish and the orders inbox delivery are stamped after commit and retried by later sweeps.
CREATE TABLE hold_expired_events (
  hold_id             BIGINT PRIMARY KEY REFERENCES seat_holds(id),
  event_key           VARCHAR(24) NOT NULL,
  payload             JSONB NOT NULL,
  created_at          TIMESTAMP NOT NULL DEFAULT now(),
  kafka_published_at  TIMESTAMP,
  orders_delivered_at TIMESTAMP,
  attempts            INT NOT NULL DEFAULT 0
);
CREATE INDEX ix_hold_expired_pending ON hold_expired_events (created_at)
  WHERE kafka_published_at IS NULL OR orders_delivered_at IS NULL;
