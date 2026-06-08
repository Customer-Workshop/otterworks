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

3. Review consumer logs for "Strict parse failed" or "Failed to parse message body" entries.
4. Check SQS queue depth in CloudWatch for the `otterworks-notifications` queue.

## Resolution Steps

1. If the chaos flag is active and was not intentionally set, remove it:
   ```
   redis-cli DEL chaos:notification-service:consumer_strict_schema
   ```
2. The consumer now falls back to the lenient parser when strict parsing fails,
   so legacy epoch-timestamp messages are handled even while the chaos flag is set.
3. Unparseable messages are always deleted from the queue after logging, preventing
   unbounded queue growth from poison messages.

## Post-Incident

- Verify SQS queue depth returns to normal after the fix is deployed.
- Review other services for similar chaos flags that lack fallback handling.
