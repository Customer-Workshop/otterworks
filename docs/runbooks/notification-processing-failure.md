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
3. Inspect the payload of a stuck message and compare it with `SqsNotificationMessage`
   (`services/notification-service/src/main/kotlin/com/otterworks/notification/model/NotificationEvent.kt`):
   ```
   aws sqs receive-message --queue-url "$SQS_QUEUE_URL" --max-number-of-messages 1 --visibility-timeout 0
   ```
   Legacy producers send `timestamp` as a Unix epoch number rather than an RFC 3339 string.
4. Check `ApproximateNumberOfMessages` / `ApproximateAgeOfOldestMessage` on the queue and the
   depth of the `-dlq` queue to size the backlog.

## Resolution Steps

1. If the chaos flag is set, clear it: `redis-cli DEL chaos:notification-service:consumer_strict_schema`
   (or `scripts/inject-bug.sh <ID> reset` for a tenant).
2. The consumer accepts both RFC 3339 and epoch `timestamp` values and deletes messages that
   cannot be deserialized instead of leaving them to cycle through the visibility timeout. If
   a new schema mismatch appears, extend the model/serializer in `NotificationEvent.kt` and
   redeploy; the backlog drains on its own once the consumer accepts the payload.
3. Redrive the DLQ once the consumer is healthy:
   `aws sqs start-message-move-task --source-arn <dlq-arn> --destination-arn <queue-arn>`.
4. Confirm `notifications_processing_errors_total` stops increasing and the alert resolves.

## Post-Incident

<!-- TODO -->
