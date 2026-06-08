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

3. Inspect a sample failed message for non-string timestamps or unexpected fields:
   ```
   aws sqs receive-message --queue-url $SQS_QUEUE_URL --max-number-of-messages 1
   ```
4. Check the `notifications_processing_errors_total` Prometheus counter for sustained growth.

## Resolution Steps

1. If the chaos flag is set, remove it:
   ```
   redis-cli DEL chaos:notification-service:consumer_strict_schema
   ```
2. Deploy the updated notification-service with the lenient parser fix (see PR history).
   The fix ensures:
   - The consumer always uses the lenient JSON parser (`ignoreUnknownKeys = true`, `isLenient = true`), accepting both RFC 3339 strings and legacy epoch integer timestamps.
   - Unparseable messages are deleted from the queue after logging, preventing unbounded queue depth growth.
3. Monitor the `notifications_processing_errors_total` counter — it should stop incrementing after the fix is deployed.
4. Verify SQS queue depth returns to normal.

## Post-Incident

- Verify the chaos flag `chaos:notification-service:consumer_strict_schema` is cleared.
- Review any messages that were dropped during the incident via the `Dropping unparseable SQS message` log entries.
- Consider adding a dead-letter queue for the notification SQS queue to capture permanently failed messages for later analysis.
