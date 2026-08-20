# Contract — Announcements

**Status: frozen.** Derived from `com.otterworks.legacyportal.announcements` plus the recorded
transcript (`baseline-transcript.json`). Read [`README.md`](README.md) first — it defines the
two error envelopes, the parity normalisation rules and the identity gap that apply here.

| | |
|---|---|
| Service module | `services/portal/announcements-service` |
| Base package | `com.otterworks.portal.announcements` |
| Port | `8101` |
| Database | `announcements-db` (PostgreSQL 16), database `announcements`, role `announcements` |
| Route prefix | `/api/announcements` — **unchanged**, no version prefix, no rename |

## 1. Resource

`Announcement` is the only aggregate. It has no relationships to anything, in this context or
any other. The wire representation is:

```json
{
  "id": 1,
  "title": "Scheduled maintenance",
  "body": "The portal will be unavailable on Sunday.",
  "published": false,
  "createdAt": "2026-08-20T20:46:25.637042Z"
}
```

Field order in the emitted JSON is `id, title, body, published, createdAt`. Jackson emits it in
declaration order today; keep the declaration order so diffs stay clean, but note that field
*order* is not part of the contract — field *set* is. No extra fields. No `updatedAt`. No
`_links`. Absent values are never omitted: all five fields are always present.

- `id` — JSON number, database identity, assigned by the database. Never supplied by a client.
- `title` — string, non-blank, max 200 characters.
- `body` — string, non-blank, max 4000 characters.
- `published` — JSON boolean, never null.
- `createdAt` — ISO-8601 instant, UTC, `Z` suffix, server-assigned at creation, immutable
  thereafter. See the precision note in the parity normalisation table.

## 2. Routes

### 2.1 `GET /api/announcements?publishedOnly={boolean}`

- `publishedOnly` is optional and **defaults to `true`**.
- `publishedOnly=true` → only rows with `published = true`, ordered by `created_at` **descending**
  (newest first). This ordering is part of the contract.
- `publishedOnly=false` → **all** rows. The monolith uses `findAll()` with no `ORDER BY`, so the
  order is whatever the database returns (insertion order in practice). The extracted service
  MUST reproduce this: **do not add an `ORDER BY` to this branch.** Adding one is a contract
  change, not an improvement. Documented as a known wart, not a bug to fix here.
- Always `200`. An empty result is `[]`, never `204` and never `{"items": []}`.
- **No pagination.** The whole table is returned. Do not add `page`/`size` parameters; an
  unrecognised query parameter is ignored by Spring and must stay ignored.
- A `publishedOnly` value that is not parseable as a boolean → `400` with the **legacy
  envelope**, carrying the converter's own message:
  ```json
  {"error": "Bad Request", "message": "Invalid boolean value [maybe]"}
  ```
  Parameter-conversion failures reach `IllegalArgumentException` and so are handled by the
  legacy advice, *unlike* bean-validation failures. Verified against the running monolith.

Response body: a JSON array of the resource in §1.

### 2.2 `GET /api/announcements/{id}`

- `200` with the resource for a known id.
- Unknown id → `404` with the **legacy envelope**:
  ```json
  {"error": "Not Found", "message": "announcement 999999 not found"}
  ```
  The `message` string is byte-exact: `announcement `, the id as supplied, ` not found`.
- `{id}` that is not a `long` → `400` with the **legacy envelope**, carrying the
  `NumberFormatException` message verbatim:
  ```json
  {"error": "Bad Request", "message": "For input string: \"abc\""}
  ```
  Same reason as §2.1: path-variable conversion failures are `IllegalArgumentException`s.

### 2.3 `POST /api/announcements`

Request:

```json
{"title": "…", "body": "…", "published": false}
```

- `title` — required, non-blank, ≤ 200 characters.
- `body` — required, non-blank, ≤ 4000 characters.
- `published` — optional JSON boolean. **Absent or `null` → `false`** (it binds to a primitive
  `boolean`). **When `true` is supplied it is honoured and the announcement is created already
  published.** The assessment page claims announcements are always created unpublished; that is
  wrong, and the transcript proves it. Reproduce the code, not the page.
- Unknown fields in the body are ignored (Jackson default), and must stay ignored.

Responses:

- `201` with the created resource. `id` and `createdAt` are server-assigned.
- Any bean-validation failure (blank/missing/oversized `title` or `body`) → `400` with the
  **default error envelope**:
  ```json
  {"timestamp": "2026-08-20T20:46:25.772+00:00", "status": 400, "error": "Bad Request", "path": "/api/announcements"}
  ```
  Note: **no `message` field, and no per-field detail.** Do not add either.
- Malformed JSON → `400`, default envelope.

There is no `Location` header today. Do not add one.

### 2.4 `POST /api/announcements/{id}/publish`

The one state transition in this context.

- `200` with the resource, `published: true`.
- **Idempotent**: publishing an already-published announcement returns `200` and the unchanged
  resource. It is not `409`, and `createdAt` does not move.
- Unknown id → `404`, legacy envelope, same message string as §2.2.
- There is **no unpublish route**. Do not add one.

### 2.5 Unmapped methods

`DELETE /api/announcements/{id}`, `PUT /api/announcements/{id}` etc. → `405` with the default
error envelope. This is Spring's own behaviour; it is contractual only in that the extracted
service must not define these routes.

## 3. State transitions

```
        POST /api/announcements {published:false}
                     │
                     ▼
              ┌─────────────┐   POST /{id}/publish   ┌───────────┐
              │ unpublished │ ─────────────────────► │ published │ ──┐
              └─────────────┘                        └───────────┘   │ POST /{id}/publish
                     ▲                                     ▲         │ (idempotent, 200)
                     │                                     └─────────┘
        POST /api/announcements {published:true} ───────────┘
```

`unpublished → published` is the only transition. There is no delete, no edit, no archive, and
no path back. Visibility in the default listing (`publishedOnly=true`) is the only observable
effect of the flag.

## 4. Data ownership

Own schema, own database, own credential. No foreign keys to anything — there are none in the
monolith and none may be introduced.

Flyway migration `V1__create_announcement.sql` must create the table **exactly as the monolith's
Hibernate mapping generates it**, plus one deliberate, documented addition:

```sql
CREATE TABLE announcement (
    id         BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title      VARCHAR(200)             NOT NULL,
    body       VARCHAR(4000)            NOT NULL,
    published  BOOLEAN                  NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

-- Deliberate addition: the default listing filters on `published` and orders by `created_at`.
-- The monolith has no index at all here (ddl-auto only ever generated the primary key).
CREATE INDEX idx_announcement_published_created_at ON announcement (published, created_at DESC);
```

- The table lives in the service's **default schema**, not in a schema named `announcements`.
  The schema name in the monolith existed only to separate contexts inside one database; a
  dedicated database makes it redundant. This is the one structural change, and it is invisible
  on the wire.
- `created_at` is stored as UTC. The application must set and read it as an `Instant`.
- `ddl-auto` is **off** (`none`) permanently. Flyway owns the schema. This is not negotiable.

Data migration from the monolith preserves `id`, `created_at`, and the identity sequence
high-water mark.

## 5. Errors — complete table

| Condition | Status | Envelope | Body |
|---|---|---|---|
| Unknown id (`GET`, `publish`) | 404 | legacy | `{"error":"Not Found","message":"announcement {id} not found"}` |
| Bean validation failure on create | 400 | default | `{"timestamp","status":400,"error":"Bad Request","path"}` |
| Malformed JSON body | 400 | default | as above |
| Unparseable `{id}` | 400 | **legacy** | `{"error":"Bad Request","message":"For input string: \"abc\""}` |
| Unparseable `publishedOnly` | 400 | **legacy** | `{"error":"Bad Request","message":"Invalid boolean value [maybe]"}` |
| Method not allowed on a mapped path | 405 | default | `{"timestamp","status":405,"error":"Method Not Allowed","path"}` |
| Unmapped path | 404 | default | `{"timestamp","status":404,"error":"Not Found","path"}` |

Both envelopes are provided by `portal-common`. Use them; do not hand-roll either, and do not
add a `@ControllerAdvice` of your own.

## 6. Health

`GET /health` → `200 {"status":"UP","service":"announcements-service"}`.

The monolith's `/health` also returns a `banner` field interpolated from a host file. **That
field is dropped**: it is the host-file-override finding from the assessment and it must not be
carried into a new service. This is the single intentional divergence from the monolith's wire
behaviour in this context, and a parity suite must assert the drop rather than ignore it.

Actuator: `/actuator/health` with liveness/readiness probes enabled, exposure limited to
`health,info`.

## 7. Out of scope for this contract

Authentication (see README §identity), pagination, an unpublish or delete route, an `updatedAt`
column, editorial workflow, and any change to `/api/announcements` path shapes. Each of these
would be a contract revision.
