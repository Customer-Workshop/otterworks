-- Set once order-confirmed has reached Kafka and both inboxes, so a redelivered payment-captured record
-- (Kafka replay after a pod loss) is a pure no-op instead of re-driving the event.
ALTER TABLE confirmations ADD COLUMN delivered_at TIMESTAMP;
