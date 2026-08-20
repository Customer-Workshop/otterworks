# Contract — Feedback

**Status: frozen.** Derived from `com.otterworks.legacyportal.feedback` plus the recorded
transcript (`baseline-transcript.json`). Read [`README.md`](README.md) first — it defines the two
error envelopes, the parity normalisation rules and the identity gap that apply here.

| | |
|---|---|
| Service module | `services/portal/feedback-service` |
| Base package | `com.otterworks.portal.feedback` |
| Port | `8103` |
| Database | `feedback-db` (PostgreSQL 16), database `feedback`, role `feedback` |
| Route prefix | `/api/feedback` — **unchanged** |

## 1. Resource

`Feedback` is append-only: three routes, one table, no update and no delete anywhere in the
monolith. Nothing reads its data except this context.

```json
{
  "id": 1,
  "userId": "u1",
  "rating": 5,
  "message": "great",
  "createdAt": "2026-08-20T20:46:26.381878Z"
}
```

Field set is exactly these five, always present, declared in that order.

- `id` — JSON number, database identity.
- `userId` — string, non-blank, max 100 characters. Caller-supplied and unvalidated; the same
  opaque identifier the user-preferences context uses, with nothing enforcing the agreement.
- `rating` — JSON integer, **1–5 inclusive**.
- `message` — string, non-blank, max 2000 characters. Note: **non-blank** — empty-string
  feedback is rejected, which is a real behaviour clients may depend on.
- `createdAt` — ISO-8601 instant, UTC, `Z` suffix, server-assigned, immutable. See parity
  normalisation for the precision note.

## 2. Routes

### 2.1 `POST /api/feedback`

Request:

```json
{"userId": "u1", "rating": 5, "message": "great"}
```

- `201` with the created resource.
- **Rating is validated twice** in the monolith: `@Min(1)`/`@Max(5)` on the DTO *and* again in
  `FeedbackService.submit`, which throws `IllegalArgumentException("rating must be between 1 and
  5")`. The two paths produce **different error bodies**, and this matters:
  - Over HTTP the **bean validation always wins** — it runs before the controller body. So
    `rating: 0` and `rating: 6` return `400` with the **default error envelope**
    (`{"timestamp","status","error","path"}`, no `message`). Verified in the transcript.
  - The service-layer check is therefore **unreachable through the HTTP surface**. Keep it
    anyway — it is the in-process guard, it is covered by the monolith's existing unit test, and
    removing it is a behaviour change at the service API even though it is invisible on the wire.
    A unit test must pin the `IllegalArgumentException` message string.
- `rating` binds to a primitive `int`, so an **absent or `null` `rating` becomes `0`**, which
  then fails `@Min(1)` → `400`, default envelope.
- Blank/missing/oversized `userId` or `message` → `400`, default envelope.
- Malformed JSON → `400`, default envelope.
- Unknown fields are ignored, and must stay ignored.

No `Location` header. Do not add one.

### 2.2 `GET /api/feedback?userId={id}`

- `userId` is a **required** query parameter. Omitting it → `400` with the **default error
  envelope** (Spring's missing-parameter error), not the legacy envelope.
- `200` with a JSON array of that user's feedback, ordered by `created_at` **descending**
  (newest first). This ordering is contractual.
- A user with no feedback → `200 []`. Never `404`.
- **No pagination and no authorization**: any caller can read any user's feedback by guessing
  the id. Reproduce as-is; see README §identity.

### 2.3 `GET /api/feedback/average-rating`

- `200` with exactly one field:
  ```json
  {"averageRating": 3.0}
  ```
- The value is the arithmetic mean of `rating` over **every row in the table**, not scoped to a
  user, and not rounded. It is serialised as a JSON number — `3.0`, not `"3.0"` and not `3`.
- **An empty table returns `0.0`**, which is indistinguishable from a genuine average of zero
  (impossible, since ratings are ≥ 1, but the shape is what matters). This is contractual:
  do **not** return `null`, `404`, or omit the field.
- **Implementation change, deliberate and invisible on the wire:** the monolith computes this by
  loading every row into the JVM (`repository.findAll()` then a stream average) — the assessment
  rates it Critical. The extracted service MUST use a SQL aggregate
  (`SELECT AVG(rating) FROM feedback`) and MUST map a `NULL` aggregate (empty table) to `0.0` so
  the response is identical. The parity suite must cover the empty-table case explicitly,
  because that is exactly where the SQL rewrite differs from the original.

### 2.4 Unmapped

`PUT`/`PATCH`/`DELETE` on `/api/feedback` or `/api/feedback/{id}` → `405` or `404` with the
default envelope. There is **no** `GET /api/feedback/{id}` route in the monolith; do not add one.

## 3. State transitions

None. Feedback is **append-only**: created, then immutable forever.

```
   (no row) ──POST /api/feedback──► created ──► (immutable; no update, no delete, no moderation)
```

The only derived state is the average, recomputed per request. There is no draft state, no
moderation flag, no soft delete. Introducing any of them is a contract revision.

## 4. Data ownership

```sql
CREATE TABLE feedback (
    id         BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_id    VARCHAR(100)                NOT NULL,
    rating     INTEGER                     NOT NULL,
    message    VARCHAR(2000)               NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

-- Deliberate addition: `findByUserIdOrderByCreatedAtDesc` is a full table scan in the monolith,
-- which has no index beyond the primary key. Flagged High in the assessment.
CREATE INDEX idx_feedback_user_id_created_at ON feedback (user_id, created_at DESC);
```

- Flyway `V1__create_feedback.sql`. `ddl-auto: none`, permanently.
- **No `CHECK (rating BETWEEN 1 AND 5)` constraint.** The monolith has none, and adding one
  would change the failure mode of any direct writer. Rating bounds stay in the application.
- Table lives in the service's default schema; the monolith's `feedback` schema qualifier is
  dropped because the database is now dedicated. Invisible on the wire.

Data migration preserves `id`, `created_at`, and the identity sequence high-water mark.

## 5. Errors — complete table

| Condition | Status | Envelope | Body |
|---|---|---|---|
| `rating` outside 1–5, or absent (binds to `0`) | 400 | default | `{"timestamp","status":400,"error":"Bad Request","path":"/api/feedback"}` |
| Blank/missing/oversized `userId` or `message` on create | 400 | default | as above |
| Malformed JSON body | 400 | default | as above |
| `GET /api/feedback` with no `userId` parameter | 400 | default | as above |
| Unknown user on `GET` | **200** | — | `[]`. Never an error. |
| Empty table on `average-rating` | **200** | — | `{"averageRating":0.0}`. Never an error. |
| Method not allowed on a mapped path | 405 | default | `{"timestamp","status":405,"error":"Method Not Allowed","path"}` |
| Unmapped path | 404 | default | `{"timestamp","status":404,"error":"Not Found","path"}` |

Like user-preferences, this context produces the `{"error","message"}` legacy envelope on **no
HTTP path** — its only `IllegalArgumentException` is shadowed by bean validation (§2.1). Use
`portal-common`'s handler unchanged anyway; do not add a `@ControllerAdvice` of your own.

## 6. Health

`GET /health` → `200 {"status":"UP","service":"feedback-service"}`. The monolith's `banner`
field is dropped — see the announcements contract §6.

Actuator: `/actuator/health` with liveness/readiness probes, exposure limited to `health,info`.

## 7. Out of scope for this contract

Authentication and ownership checks (see README §identity), pagination on the per-user list,
`GET /api/feedback/{id}`, moderation/deletion, a rating `CHECK` constraint, and scoping the
average by user or time window. Each would be a contract revision.
