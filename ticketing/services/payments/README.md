# payments — extracted from the BoxOffice monolith (PaymentBean + HoldExpiryBean's payment side)

Spring Boot 3 / Java 21 / Maven. Owns `payments` and `payment_attempts` (Flyway `V1__payments.sql`) in its own
PostgreSQL. It is the only real Kafka consumer of the first slice: a Deployment scaled 0..6 by KEDA on
`<token>-order-placed` lag.

| | |
|---|---|
| consumes | `<token>-order-placed` (key `orderRef`, group `<token>-payments`, `enable.auto.commit=false`) |
| publishes | `<token>-payment-captured`, `<token>-payment-failed` (key `orderRef`, 6 partitions) |
| HTTP fan-out before the offset commit | captured → `POST $CONFIRMATIONS_URL/events/payment-captured`; failed → `POST $ORDERS_URL/events/payment-failed` and `POST $SEATS_URL/events/payment-failed` |
| API | `GET /api/payments/{orderRef}` (404 unknown), `GET /stats`, `GET /actuator/health[/readiness|/liveness]`, `GET /actuator/prometheus` |

Per record: `payments.order_ref` is looked up first. Present → duplicate delivery: no gateway call, no rows,
`duplicatesSuppressed++`, the stored outcome event is re-driven. `holdExpiresAt` in the past → `HOLD_EXPIRED`
(payment `EXPIRED`, order `CANCELLED`, no gateway call). Otherwise the synthetic gateway is charged with the
monolith's rules (card `0000` declines, `GATEWAY_DECLINE_PCT`, latency U(`GATEWAY_MIN_MS`,`GATEWAY_MAX_MS`),
`PAYMENT_TIMEOUT_MS` → `TIMEOUT` with null gateway ref) and attempt + payment are written in one transaction;
the offset is acknowledged only after the Kafka record and the HTTP inboxes have been delivered.

## Run

```bash
mvn -B verify                                   # unit + contract tests (H2 + embedded Kafka, no Docker)
docker build -t payments .                      # multi-stage, temurin 21 JRE, uid 10001
TOKEN=tkt01 IMAGE=<ecr>/payments:tkt01-<sha> envsubst '${TOKEN} ${IMAGE}' < k8s/30-payments.yaml
```

Environment: `TOKEN`, `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`, `KAFKA_BOOTSTRAP`, `KAFKA_CONCURRENCY`,
`CONFIRMATIONS_URL`, `ORDERS_URL`, `SEATS_URL` (blank = skip the HTTP fan-out), `HOLD_MINUTES`,
`PAYMENT_TIMEOUT_MS`, `GATEWAY_MIN_MS`, `GATEWAY_MAX_MS`, `GATEWAY_DECLINE_PCT`.

## Contract fixtures

`src/test/resources/contracts/*.json` are the monolith's recorded responses (fresh `seed.sql`, performance 1,
two seats, `POST /api/purchase`; the timeout case ran the monolith with `PAYMENT_TIMEOUT_MS=1`; hold expiry
used `POST /api/admin/expire-holds`). `MonolithContractTest` replays each as an `order-placed` record and
asserts the same payment status, amount, attempt outcome/latency, gateway-ref presence and stats.

## k8s/

`10-db.yaml` (Postgres Deployment + ClusterIP Service), `20-topics.yaml` (KafkaTopics it produces,
`kafka.strimzi.io/v1`, 6 partitions), `30-payments.yaml` (Deployment + ClusterIP Service),
`40-observability.yaml` (ServiceMonitor, NetworkPolicy), `50-keda.yaml` (ScaledObject min 0 / max 6,
`lagThreshold` 40, cooldown 60s). All names `${TOKEN}-payments*`, labels `demo.otterworks.app/run-token`
and `demo.otterworks.app/side: after`, namespace `${TOKEN}-after`.
