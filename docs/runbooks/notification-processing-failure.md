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

<!-- TODO: Complete investigation steps -->

## Resolution Steps

1. Remove the chaos flag from Redis to stop activating the strict parser:
   ```
   redis-cli DEL chaos:notification-service:consumer_strict_schema
   ```
2. The consumer now includes a lenient-parser fallback: when the strict parser
   fails (e.g. on legacy epoch-format timestamps), the lenient parser retries
   the message before giving up.  Deploy the updated notification-service image
   to pick up the fix.
3. Monitor the `notifications.processing.errors` metric and SQS queue depth to
   confirm recovery.

## Post-Incident

- Verify SQS queue depth returns to normal after deployment.
- Ensure no messages were permanently lost (failed messages were never deleted,
  so they will be reprocessed once the fix is deployed).
- Review chaos flag TTL settings to prevent unintended production impact.
