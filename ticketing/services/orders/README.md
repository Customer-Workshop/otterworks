# orders

Order placement for the ticketing after-state. Spring Boot 3 / Java 21 / Maven, its own PostgreSQL
(Flyway), transactional outbox to Kafka.

## Owns

| Tables | `orders`, `order_items`, `order_fees`, `outbox` |
|---|---|
| Reference copies (Flyway seed, same synthetic data as `ticketing/monolith/db/seed.sql`) | `venues`, `price_zones`, `events`, `performances`, `performance_price_levels`, `promo_codes`, `delivery_methods` |
| Publishes | `order-placed` → topic `${TOKEN}-order-placed`, key `orderRef` (outbox relay) |
| Consumes (HTTP inboxes) | `POST /events/payment-failed`, `POST /events/order-confirmed`, `POST /events/hold-expired` |

Seats, holds, payments and tickets live elsewhere: placement calls seats `POST /api/holds` (or
`GET /api/holds/{holdRef}` for `/api/orders`) and prices the held seats from the zone tally seats returns.

## API

| Route | Behaviour |
|---|---|
| `POST /api/purchase` | legacy body `{performanceId,email,quantity?,section?,promoCode?,delivery?,cardLast4?,clientRef?}` → **202** `{orderRef,status:PENDING_PAYMENT,totalCents,tickets:0,paymentOutcome:PENDING}`; seats errors pass through (`409 SOLD_OUT`, `404 NOT_FOUND`, `400 BAD_QUANTITY`/`BAD_REQUEST`); same `clientRef` replays the same order without a second hold |
| `POST /api/orders` | `{holdRef,email,...}` from an existing hold; `410 HOLD_EXPIRED` when seats says the hold is not active |
| `GET /api/orders/{ref}` | order (`order_ref,status,subtotal_cents,fees_cents,total_cents,channel,email,event_title,starts_at,venue_name,created_at`) + `items[]` + `fees[]` + `paymentOutcome`; `404 NOT_FOUND` |
| `GET /stats` (also `/api/stats`) | `{ordersTotal, ordersByStatus, ordersByPaymentOutcome, outboxUnpublished, promoUses, ...}` |
| `GET /actuator/health[/readiness|/liveness]`, `GET /actuator/prometheus` | probes; metrics `orders_outbox_unpublished`, `orders_outbox_published_total`, `orders_placed_total` |

Status machine: `PENDING_PAYMENT → CONFIRMED | PAYMENT_FAILED | PAYMENT_TIMEOUT | CANCELLED`; transitions
apply only from `PENDING_PAYMENT`, so every inbox is idempotent and late/duplicate events are no-ops.
Pricing is the monolith's: face × (demand factor + uplift), 5 % uplift per 10 % of the zone not available
(cap 40 %), promo `percent_off` on the subtotal, 12 % service fee, 250 ¢ facility fee per seat, delivery
0/150/300 ¢; promo `used_count` increments at placement.

## Runtime (`k8s/`, rendered with `envsubst '${TOKEN} ${IMAGE}'`)

```
export TOKEN=tkt01 IMAGE=599083837640.dkr.ecr.us-east-1.amazonaws.com/otterworks-demo/ticketing/orders:tkt01-<sha>
for f in k8s/*.yaml; do envsubst '${TOKEN} ${IMAGE}' < "$f" | kubectl apply -f -; done
```

* `10-orders-db.yaml` — PostgreSQL 16 Deployment + ClusterIP Service + credentials Secret (emptyDir; Flyway re-creates and re-seeds on a fresh volume).
* `20-kafka-topic.yaml` — `KafkaTopic ${TOKEN}-order-placed` (6 partitions).
* `30-orders-ksvc.yaml` — Knative Service `${TOKEN}-orders`, rps autoscaling, min 0 / max 6. Cluster URL `http://${TOKEN}-orders.${TOKEN}-after.svc.cluster.local` (Kourier). Relay disabled in this role.
* `40-outbox-relay.yaml` — Deployment `${TOKEN}-orders-outbox-relay` (same image, `ORDERS_RELAY_ENABLED=true`) + ClusterIP Service + KEDA `ScaledObject` (postgresql scaler on `SELECT count(*) FROM outbox WHERE published_at IS NULL`, 0..1 replicas — one replica keeps outbox id order). It keeps draining when the Knative path is at zero.
* `50-monitoring.yaml` — PodMonitor for the Knative pods (`user-port`, bypasses queue-proxy) + ServiceMonitor for the relay.
* `60-networkpolicy.yaml` — ingress to all orders pods from the namespace, `ingress-nginx`, `kourier-system`, `knative-serving`, `keda`, `monitoring`.

Environment: `TOKEN`, `DB_URL/DB_USER/DB_PASSWORD/DB_POOL_SIZE`, `SEATS_BASE_URL`
(`http://${TOKEN}-seats.${TOKEN}-after.svc.cluster.local`), `KAFKA_BOOTSTRAP`, `ORDERS_RELAY_ENABLED`,
`ORDERS_CHANNEL` (default `API`).

## Build / test

```
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 mvn -B verify      # unit tests (surefire) + *IT (failsafe, embedded PostgreSQL, no Docker)
docker build -t <ecr>/otterworks-demo/ticketing/orders:tkt01-<sha> .
```

`src/test/resources/contracts/*.json` were recorded from the monolith before-state by `record.py`;
`ContractIT` replays each case against this service (seats stubbed with the same seed's zone sizes) and
asserts the same totals, statuses, seat counts and error codes after the payment/confirmation events.
