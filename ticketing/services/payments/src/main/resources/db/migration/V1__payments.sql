-- Tables the payments service takes over from the monolith (schema.sql payments / payment_attempts),
-- re-keyed by order reference. order_ref is the idempotency key: a replayed order-placed record is a no-op.
-- status: CAPTURED, DECLINED, TIMEOUT (monolith) + EXPIRED (hold lapsed before the record was consumed).
CREATE TABLE payments (
  id                    BIGSERIAL PRIMARY KEY,
  order_ref             VARCHAR(40) NOT NULL,
  hold_ref              VARCHAR(40),
  amount_cents          BIGINT NOT NULL,
  currency              CHAR(3) NOT NULL DEFAULT 'USD',
  status                VARCHAR(16) NOT NULL,
  gateway_ref           VARCHAR(40),
  card_last4            CHAR(4),
  provider              VARCHAR(16) NOT NULL DEFAULT 'SYNTH',
  duplicate_deliveries  INT NOT NULL DEFAULT 0,
  created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  CONSTRAINT uq_payments_order_ref UNIQUE (order_ref),
  CONSTRAINT ck_payments_status CHECK (status IN ('CAPTURED', 'DECLINED', 'TIMEOUT', 'EXPIRED'))
);

CREATE TABLE payment_attempts (
  id          BIGSERIAL PRIMARY KEY,
  order_ref   VARCHAR(40) NOT NULL,
  attempt_no  INT NOT NULL,
  outcome     VARCHAR(16) NOT NULL,
  latency_ms  INT NOT NULL,
  created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  CONSTRAINT uq_payment_attempts_order_attempt UNIQUE (order_ref, attempt_no)
);
CREATE INDEX ix_payments_status ON payments (status);
