# payments — extracted from the BoxOffice monolith (PaymentBean + HoldExpiryBean's payment side)

Spring Boot 3 / Java 21 / Maven. Owns `payments`, `payment_attempts` (Flyway `V1__payments.sql`) and the
`outcome_deliveries` outbox (`V2__outcome_deliveries.sql`) in its own PostgreSQL. It is the only real Kafka consumer of the first slice: a Deployment scaled 0..6 by KEDA on
`<token>-order-placed` lag.

| | |
|---|---|
| consumes | `<token>-order-placed` (key `orderRef`, group `<token>-payments`, `enable.auto.commit=false`) |
| publishes | `<token>-payment-captured`, `<token>-payment-failed` (key `orderRef`, 6 partitions) |
| HTTP fan-out via the outbox | captured → `POST $CONFIRMATIONS_URL/events/payment-captured`; failed → `POST $ORDERS_URL/events/payment-failed` and `POST $SEATS_URL/events/payment-failed` — rows in `outcome_deliveries`, written in the payment transaction, POSTed by `InboxRelay` |
| API | `GET /api/payments/{orderRef}` (404 unknown), `GET /stats`, `GET /actuator/health[/readiness|/liveness]`, `GET /actuator/prometheus` |

Per record: `payments.order_ref` is looked up first. Present → duplicate delivery: no gateway call, no rows,
`duplicatesSuppressed++`, the stored outcome event is re-driven. `holdExpiresAt` in the past → `HOLD_EXPIRED`
(payment `EXPIRED`, order `CANCELLED`, no gateway call). Otherwise the synthetic gateway is charged with the
monolith's rules (card `0000` declines, `GATEWAY_DECLINE_PCT`, latency U(`GATEWAY_MIN_MS`,`GATEWAY_MAX_MS`),
`PAYMENT_TIMEOUT_MS` → `TIMEOUT` with null gateway ref) and attempt + payment + `outcome_deliveries` rows are
written in one transaction; the offset is acknowledged once the Kafka outcome record is acknowledged. The HTTP
inboxes are never on the consumer path: `InboxRelay` (every replica, plus the `<token>-payments-relay`
Deployment that KEDA scales 0..2 on pending rows) leases due rows with `FOR UPDATE SKIP LOCKED`, POSTs with 2 s /
5 s connect/read timeouts, retries with exponential backoff (1 s → 30 s) and marks a row `given_up_at` after
`RELAY_MAX_ATTEMPTS` (40, about 20 min); the Kafka `payment-captured`/`payment-failed` record stays the durable
outcome. `(order_ref, target)` is unique, so a redelivered `order-placed` never enqueues the same POST twice.
An unreachable sibling therefore costs nothing but a delayed inbox call (verify-1 finding: the synchronous POST
plus `FixedBackOff(2000, UNLIMITED_ATTEMPTS)` had pinned all six partitions at offset 0 while orders expired).

## Run

```bash
mvn -B verify                                   # unit + contract tests (H2 + embedded Kafka, no Docker)
docker build -t payments .                      # multi-stage, temurin 21 JRE, uid 10001
TOKEN=tkt01 IMAGE=<ecr>/payments:tkt01-<sha> envsubst '${TOKEN} ${IMAGE}' < k8s/30-payments.yaml
```

Environment: `TOKEN`, `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`, `KAFKA_BOOTSTRAP`, `KAFKA_CONCURRENCY`,
`CONFIRMATIONS_URL`, `ORDERS_URL`, `SEATS_URL` (blank = skip the HTTP fan-out), `HOLD_MINUTES`,
`PAYMENT_TIMEOUT_MS`, `GATEWAY_MIN_MS`, `GATEWAY_MAX_MS`, `GATEWAY_DECLINE_PCT`; relay: `KAFKA_LISTENER_AUTO_STARTUP`
(false in the relay Deployment), `RELAY_POLL_MS`, `RELAY_BATCH_SIZE`, `RELAY_LEASE_MS`, `RELAY_BACKOFF_MS`,
`RELAY_MAX_BACKOFF_MS`, `RELAY_MAX_ATTEMPTS`, `RELAY_THREADS`. Metrics: `payments_inbox_deliveries_total{target,result}`,
`payments_inbox_deliveries_pending`; `GET /stats` adds `deliveriesPending` / `deliveriesGivenUp`.

## Contract fixtures

`src/test/resources/contracts/*.json` are the monolith's recorded responses (fresh `seed.sql`, performance 1,
two seats, `POST /api/purchase`; the timeout case ran the monolith with `PAYMENT_TIMEOUT_MS=1`; hold expiry
used `POST /api/admin/expire-holds`). `MonolithContractTest` replays each as an `order-placed` record and
asserts the same payment status, amount, attempt outcome/latency, gateway-ref presence and stats.

## k8s/

`10-db.yaml` (Postgres Deployment + ClusterIP Service), `20-topics.yaml` (KafkaTopics it produces,
`kafka.strimzi.io/v1`, 6 partitions), `30-payments.yaml` (Deployment + ClusterIP Service), `35-inbox-relay.yaml`
(DB Secret, `${TOKEN}-payments-relay` Deployment + Service + ServiceMonitor, TriggerAuthentication, ScaledObject
min 0 / max 2 on pending `outcome_deliveries`), `40-observability.yaml` (ServiceMonitor, NetworkPolicy),
`50-keda.yaml` (ScaledObject min 0 / max 6, `lagThreshold` 40, cooldown 60s). All names `${TOKEN}-payments*`, labels `demo.otterworks.app/run-token`
and `demo.otterworks.app/side: after`, namespace `${TOKEN}-after`.
