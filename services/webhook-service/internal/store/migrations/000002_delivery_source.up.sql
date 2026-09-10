ALTER TABLE webhook.deliveries ADD COLUMN IF NOT EXISTS source_message_id text NULL;
CREATE UNIQUE INDEX IF NOT EXISTS deliveries_source_unique
  ON webhook.deliveries(subscription_id, source_message_id)
  WHERE source_message_id IS NOT NULL;
