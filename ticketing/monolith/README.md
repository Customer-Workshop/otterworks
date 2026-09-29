# BoxOffice — synthetic ticketing monolith (before state)

A deliberately undecomposed Jakarta EE 10 application on WildFly 32, used as the
**before state** of the ticketing modernization demo. Every name, venue, promoter,
performer and customer in it is invented; e-mail addresses use `example.test`.

| Shape | Where |
|---|---|
| 13 session beans (12 `@Stateless`, 1 `@Stateful` cart) | `src/main/java/com/boxoffice/*/*Bean.java` |
| 20 JSPs + 2 fragments behind one front-controller servlet | `src/main/webapp/WEB-INF/jsp`, `web/FrontControllerServlet.java` |
| One schema, 30 tables, every module joins across it | `db/schema.sql` |
| Deterministic synthetic seed (5,000 customers, 24 performances) | `db/seed.sql` |
| Utility package imported by every module (`Db`, `Money`, `Refs`, `Config`, `AuditLog`, `Json`) | `src/main/java/com/boxoffice/common` |
| Nightly settlement timer (02:15) | `settlement/SettlementBean.java` |
| Seat holds that expire (sweeper every minute) | `inventory/SeatHoldBean.java`, `inventory/HoldExpiryBean.java` |
| Payment step that can time out or decline | `payment/PaymentGatewayClient.java`, `payment/PaymentBean.java` |

The purchase path (`POST /api/purchase`, or the storefront at `/app/`) runs customer
lookup, seat hold, pricing, order, payment and confirmation in **one JTA transaction**
in `sales/PurchaseFacadeBean.java` — the coupling the demo decomposes.

## Run locally

```bash
docker compose up -d --build          # Postgres 16 + WildFly, app CPU-limited to MONOLITH_CPUS (0.5)
curl -s localhost:8080/api/health
curl -s -XPOST localhost:8080/api/purchase -H 'Content-Type: application/json' \
  -d '{"performanceId":1,"email":"fan00001@example.test","quantity":2}'
curl -s localhost:8080/api/stats
```

`cardLast4: "0000"` always declines; `GATEWAY_MAX_MS` above `PAYMENT_TIMEOUT_MS` produces timeouts.

## Knobs (environment)

| Variable | Default | Effect |
|---|---|---|
| `PRICING_PASSES` | 3 (compose/k8s: 200) | Passes over the full seat map per quote — the CPU cost that makes one replica saturate |
| `HOLD_MINUTES` | 10 | Seat-hold lifetime |
| `PAYMENT_TIMEOUT_MS` | 4000 | Gateway call abandoned after this |
| `GATEWAY_MIN_MS` / `GATEWAY_MAX_MS` | 40 / 120 | Simulated gateway latency |
| `GATEWAY_DECLINE_PCT` | 0 | Random decline rate |

## Build and test

```bash
mvn -B -s docker/maven-settings.xml verify   # JDK 21
```
