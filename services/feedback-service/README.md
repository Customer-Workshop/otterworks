# feedback-service

The **feedback** bounded context, extracted out of the `legacy-portal` modular monolith into its
own deployable. It owns the `feedback` schema **exclusively** — `legacy-portal` no longer creates
or touches it.

Stack: **Java 17 / Spring Boot 3.2 / `jakarta.*`** (the upgrade target listed in the monolith's
README). The monolith stays on Java 11 / Boot 2.7.

## Routes

| Method | Route | Notes |
|---|---|---|
| `POST` | `/api/feedback` | `201 Created`; body `{userId, rating, message}`; `userId` non-blank ≤100, `rating` 1–5, `message` non-blank ≤2000 |
| `GET` | `/api/feedback?userId=` | newest first |
| `GET` | `/api/feedback/average-rating` | `{"averageRating": <double>}` |
| `GET` | `/health` | `{"status":"UP","service":"feedback-service"}` (Actuator's `/actuator/health` is also enabled) |

Contracts are byte-identical to the monolith's, including validation behavior and the error body
produced by `GlobalExceptionHandler` (`{"error": "<reason phrase>", "message": "<detail>"}` for a
service-level `IllegalArgumentException`, e.g. a rating outside 1–5 that bypasses bean validation).

### Average rating on empty input

**`0.0`** — not `null`, not a 404. `FeedbackService.averageRating()` returns `0.0` when the table
is empty, so `GET /api/feedback/average-rating` answers `200 {"averageRating":0.0}`. This is the
monolith's existing behavior, preserved deliberately and pinned by
`FeedbackServiceEmptyInputTest`.

## Build & test

```bash
cd services/feedback-service
./mvnw verify        # compile + run unit tests (uses embedded H2)
```

## Run

### Local (embedded H2, self-contained)

```bash
./scripts/run-local.sh
curl http://localhost:8096/health
```

### With a real PostgreSQL (Docker Compose)

```bash
docker compose up --build
curl http://localhost:8096/health
docker compose down -v
```

The `feedback` schema is created by [`scripts/initdb.sql`](scripts/initdb.sql), moved here from
`services/legacy-portal/scripts/initdb.sql`. Port **8096** is clear of `legacy-portal`'s 8095 and
the 8081–8091 range used by the golden app's services. Like `legacy-portal`, this stack is
intentionally separate from the Helm/EKS deploy path.
