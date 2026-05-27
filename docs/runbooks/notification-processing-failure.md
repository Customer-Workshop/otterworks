# Runbook: Notification Processing Failures

**Severity:** Critical

## Alert

`NotificationConsumerProcessingErrors` -- fires when the notification-service SQS consumer is generating sustained processing errors.

## Symptoms

- Users stop receiving notifications (email, in-app) for shared files and document updates.
- The Chaos Scenarios dashboard shows non-zero processing error rate on the notification-service panel.
- SQS queue depth grows unboundedly as failed messages re-enter after visibility timeout.

## Investigation Steps

1. Check notification-service consumer logs for deserialization errors:
   ```
   kubectl logs -l app=notification-service --tail=100 -n otterworks | grep -i "deseriali\|timestamp\|schema"
   ```
2. Check whether the chaos flag `chaos:notification-service:consumer_strict_schema` is set in Redis:
   ```
   redis-cli EXISTS chaos:notification-service:consumer_strict_schema
   ```

3. Inspect the SQS queue depth to confirm unbounded growth:
   ```
   aws sqs get-queue-attributes --queue-url $SQS_QUEUE_URL --attribute-names ApproximateNumberOfMessages
   ```
4. Check for legacy messages with integer timestamps in the queue:
   ```
   aws sqs receive-message --queue-url $SQS_QUEUE_URL --max-number-of-messages 5
   ```

## Resolution Steps

1. If the chaos flag is set, remove it:
   ```
   redis-cli DEL chaos:notification-service:consumer_strict_schema
   ```
2. The consumer now falls back to the lenient JSON parser when the strict parser
   fails, so legacy messages with integer timestamps are handled gracefully.
3. Messages that fail all parsing attempts are deleted from the queue to prevent
   poison pills from causing unbounded queue growth.
4. Monitor the `notifications_processing_errors_total` metric to confirm the
   error rate drops to zero after deploying the fix.

## Post-Incident

1. Verify the SQS queue depth returns to normal after the fix is deployed.
2. Consider standardizing all upstream services on RFC 3339 timestamps to
   eliminate the need for lenient parsing long-term.
