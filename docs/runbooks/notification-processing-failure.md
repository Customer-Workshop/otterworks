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
   A recurring `Failed to parse message body` / `SerializationException` with a
   numeric `timestamp` field confirms a schema-mismatch failure.
2. Check whether the chaos flag `chaos:notification-service:consumer_strict_schema` is set in Redis:
   ```
   redis-cli EXISTS chaos:notification-service:consumer_strict_schema
   ```
   A value of `1` means the consumer has been switched to the strict JSON parser.
3. Confirm the failure mode: messages are not being deleted (delete count flat while
   receive count climbs) and queue depth (`ApproximateNumberOfMessagesVisible`) grows.

## Root Cause

The consumer selects a JSON parser based on the chaos flag. When
`chaos:notification-service:consumer_strict_schema` is set, it uses a strict parser
(`isLenient = false`). Legacy producers (older service versions) emit `timestamp` as a
Unix epoch integer rather than an RFC 3339 string. The strict parser cannot coerce a
numeric token into the `String timestamp` field, throws `SerializationException`, and the
message is never deleted. After the SQS visibility timeout the message reappears, so the
queue grows without bound while the consumer keeps erroring.

## Resolution Steps

**Immediate mitigation (operational):**

1. Clear the chaos flag to return the consumer to lenient parsing:
   ```
   redis-cli DEL chaos:notification-service:consumer_strict_schema
   ```
   or use the Admin Dashboard → Incidents → notification-service "reset" action.
2. Confirm error rate drops to zero and queue depth drains as messages are processed and
   deleted.

**Durable fix (code):**

- The `timestamp` field on `SqsNotificationMessage` / `NotificationEvent` uses a tolerant
  deserializer (`LenientTimestampSerializer`) that accepts both RFC 3339 strings and Unix
  epoch integers (seconds or milliseconds), normalizing to an ISO-8601 string. This means
  legacy epoch-int messages deserialize successfully even under the strict parser, so the
  schema mismatch no longer produces consumer errors or unbounded queue growth.

## Post-Incident

- Verify the notification backlog fully drained and users received queued notifications.
- Confirm producers are emitting RFC 3339 timestamps going forward; the tolerant
  deserializer covers any remaining legacy epoch-int publishers.
- Follow-up hardening to consider: attach a dead-letter queue (DLQ) with a redrive policy
  so any genuinely unparseable message is quarantined after N receives instead of cycling
  forever, and add an alert on queue-age / DLQ depth.
