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
3. Confirm the failure signature: `parseMessage` returns `null` on messages
   whose `timestamp` is a Unix epoch **integer** (legacy producers) instead of
   an RFC 3339 string. Under the strict parser these fail deserialization, the
   `notifications.processing.errors` counter climbs, and the message is never
   deleted — so it re-enters the queue after the visibility timeout and queue
   depth grows unbounded.
4. Inspect SQS queue depth (`ApproximateNumberOfMessages`) to gauge blast
   radius and how far behind delivery is.

## Resolution Steps

1. **Immediate mitigation (operator):** clear the chaos flag so the consumer
   returns to the lenient parser:
   ```
   redis-cli DEL chaos:notification-service:consumer_strict_schema
   ```
   The backlog then drains as messages parse and are deleted.
2. **Permanent fix (code):** the consumer now normalizes `timestamp` via
   `FlexibleTimestampSerializer`, which accepts both RFC 3339 strings and Unix
   epoch integers regardless of the parser's strictness, so legacy messages no
   longer wedge the queue.

## Post-Incident

- Verify queue depth returns to baseline and the processing-error rate on the
  Chaos Scenarios dashboard drops to zero.
- Ensure producers standardize on RFC 3339 timestamps; the consumer accepts
  both forms defensively but a single wire format is preferred.
