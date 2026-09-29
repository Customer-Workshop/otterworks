# seats service (tkt01)

Extracted from the Jakarta EE monolith (`ticketing/monolith`): **seat allocation** — inventory,
holds and hold items. Spring Boot 3.3 / Java 21 / Maven, PostgreSQL 16, Flyway, JDBC.

## Owns

| table | role |
|-------|------|
| `seat_inventory` | one row per (performance, seat): `AVAILABLE` / `HELD` / `SOLD`, `hold_id`, `order_ref` |
| `seat_holds` | `ACTIVE` → `CONVERTED` / `EXPIRED` / `RELEASED`, `expires_at = now + HOLD_MINUTES` (10) |
| `seat_hold_items` | seats in a hold |
| `inbox` | idempotency for consumed events, keyed `(event_name, orderRef)` |
| `hold_expired_events` | pending/delivered `hold-expired` records (Kafka leg + orders HTTP leg stamped separately, retried on the next sweep) |

Read-only reference copies (`V2__reference_seed.sql`, same synthetic data as `ticketing/monolith/db/seed.sql`):
`venues`, `venue_sections`, `price_zones`, `seats`, `performances` — 3 venues, 24 performances,
152 400 inventory rows.

## API

| method / path | behaviour |
|---------------|-----------|
| `POST /api/holds` `{performanceId, quantity?, section?, customerEmail?}` | best-available hold (`FOR UPDATE SKIP LOCKED`, ordered by section, row, seat), 201 `{holdRef, performanceId, expiresAt, seats[], zoneTally[]}`; 404 `NOT_FOUND`, 400 `BAD_QUANTITY` (`quantity < 1` or `> max_per_order`), 409 `SOLD_OUT`. `quantity` defaults to 2 like the legacy `/api/purchase`. |
| `GET /api/holds/{holdRef}` | `{holdRef, status, active, expiresAt, performanceId, orderRef, seats[]}`; 404 |
| `POST /api/holds/{holdRef}/order` `{orderRef}` | optional: orders stamps its `orderRef` on a pending hold so `hold-expired` is keyed by `orderRef` |
| `GET /api/performances/{id}/availability` | `{available, held, sold}` (legacy shape) |
| `POST /api/holds/sweep` / `POST /api/admin/expire-holds` | expire ≤ 500 `ACTIVE` holds with `expires_at < now()`, `{released}`; publishes and delivers `hold-expired` |
| `POST /events/payment-failed` | inbox (key `orderRef`): hold `RELEASED`, seats `AVAILABLE`, `order_ref` cleared |
| `POST /events/order-confirmed` | inbox (key `orderRef`): hold `CONVERTED`, seats `SOLD` with `order_ref` |
| `GET /stats` (alias `/api/stats`) | `{seatsAvailable, seatsHeld, seatsSold, holdsByStatus{ACTIVE,CONVERTED,EXPIRED,RELEASED}, inboxEvents, holdExpiredPending}` |
| `GET /actuator/health[/readiness|/liveness]`, `GET /actuator/prometheus` | probes, Micrometer |

Inbox responses are `200 {event, key, applied, detail}`; a replay is `applied: false, detail: "duplicate"`.
Errors are `{error, message}` like the monolith's `PurchaseResource`.

## Events

* publishes `hold-expired` → topic `${TOKEN}-hold-expired` (key `orderRef` if attached, else `holdRef`) and
  `POST ${ORDERS_BASE_URL}/events/hold-expired` with the same JSON
  `{holdRef, performanceId, orderRef, seatInventoryIds[], expiredAt}`.
* consumes `payment-failed`, `order-confirmed` via the HTTP inboxes above (request-driven service, no Kafka consumer).

## Configuration (env)

`SEATS_DB_URL` / `SEATS_DB_USER` / `SEATS_DB_PASSWORD`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_ENABLED`,
`ORDERS_BASE_URL`, `ORDERS_INBOX_ENABLED`, `HOLD_MINUTES` (10), `SWEEP_BATCH_SIZE` (500), `TOKEN` (tkt01).

## Build & test

```sh
mvn -B verify                # unit + contract tests on an embedded PostgreSQL 16 (no Docker needed)
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
docker build -t seats .      # multi-stage, non-root, temurin 21 JRE
```

Contract fixtures in `src/test/resources/contracts/` were recorded from the monolith
(`otterworks-demo/ticketing/monolith:42b55d2` on the pristine seed, plus the live `tkt01-before` host) and
the tests replay the same scenario against this service. Deployment manifests: see `k8s/README.md`.
