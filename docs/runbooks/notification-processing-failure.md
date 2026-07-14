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

3. Confirm the symptom in metrics: the `notifications.processing.errors` counter is climbing
   while `notifications.processed` is flat, and SQS `ApproximateNumberOfMessagesVisible` for
   the notification queue is growing (failed messages are never deleted, so they re-enter
   after the visibility timeout).
4. Inspect a failing message body. The root cause is a schema mismatch: legacy producers emit
   the `timestamp` field as a Unix epoch **integer** (e.g. `1704067200`), while the consumer's
   strict JSON parser only accepts an RFC 3339 **string** (e.g. `"2024-01-01T00:00:00Z"`),
   throwing `SerializationException` on every legacy event.

## Resolution Steps

There are two levers — an immediate mitigation and the durable code fix.

**Immediate mitigation (per-tenant, no deploy):** clear the chaos flag so the consumer falls
back to the lenient parser.

```
redis-cli DEL chaos:notification-service:consumer_strict_schema
```

Processing errors should stop within one poll cycle and the queue should drain as backlog is
consumed and deleted.

**Durable fix (code):** make timestamp deserialization tolerant of both formats so legacy
epoch-int events parse regardless of parser strictness. This is implemented via
`FlexibleTimestampSerializer` on the `timestamp` field of `SqsNotificationMessage` /
`NotificationEvent`; both epoch integers and RFC 3339 strings are normalized to a `String`.

## Post-Incident

- Verify queue depth has returned to baseline and `notifications.processed` is advancing.
- Follow-up hardening: route messages that genuinely cannot be deserialized to a dead-letter
  queue (or delete after logging) so a single poison message can never grow the queue
  unboundedly. Today unparseable messages are logged and left on the queue to redeliver.
- Add a producer/consumer contract test to catch timestamp/schema drift before release.
