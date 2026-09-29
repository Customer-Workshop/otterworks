-- Outbox for the HTTP inbox fan-out (confirmations for payment-captured; orders and seats for payment-failed).
-- A row is written in the same transaction as the payment and relayed asynchronously by InboxRelay, so an
-- unreachable inbox never blocks the Kafka partition: the consumer commits after the DB transaction + Kafka send.
-- (order_ref, target) is unique so a redelivered order-placed record cannot enqueue the same POST twice.
CREATE TABLE outcome_deliveries (
  id               BIGSERIAL PRIMARY KEY,
  order_ref        VARCHAR(40) NOT NULL,
  target           VARCHAR(16) NOT NULL,
  event            VARCHAR(24) NOT NULL,
  payload          TEXT NOT NULL,
  attempts         INT NOT NULL DEFAULT 0,
  next_attempt_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  last_error       VARCHAR(255),
  delivered_at     TIMESTAMP WITH TIME ZONE,
  given_up_at      TIMESTAMP WITH TIME ZONE,
  created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  CONSTRAINT uq_outcome_deliveries_order_target UNIQUE (order_ref, target),
  CONSTRAINT ck_outcome_deliveries_target CHECK (target IN ('CONFIRMATIONS', 'ORDERS', 'SEATS'))
);
CREATE INDEX ix_outcome_deliveries_pending ON outcome_deliveries (delivered_at, given_up_at, next_attempt_at);
