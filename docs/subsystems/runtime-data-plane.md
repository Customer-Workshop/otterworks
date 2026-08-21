# Subsystem: Application Runtime Data Plane

Status: written from source inspection of `main`. Every claim below is tied to a
repo-relative path; anything not directly observed in code is labelled
**(inference)**.

---

## 1. Purpose & scope

The runtime data plane is the **live, user-facing request path**: the HTTP/WebSocket
edge plus the five polyglot services that serve files, documents, realtime
collaboration and search, and the datastores those services own.

In scope:

| Concern | Owned by |
| --- | --- |
| North-south HTTP edge, JWT enforcement, identity forwarding, rate limiting, circuit breaking | `services/api-gateway/` |
| Binary object storage + file/folder/share/version metadata | `services/file-service/` |
| Structured documents, versions, comments, templates | `services/document-service/` |
| Realtime co-editing, presence, Yjs state | `services/collab-service/` |
| Full-text index and query | `services/search-service/` |
| Cross-service contracts | `shared/openapi/`, `shared/events/`, `shared/proto/` |
| Local runtime topology | `docker-compose.yml`, `docker-compose.infra.yml`, `Makefile` |

Explicitly **not** in scope of this document:

- **Token issuance.** `services/auth-service/` (Java/Spring Boot) is a *dependency*: it
  mints the JWTs the data plane verifies. Only its token format is covered
  (§4.1); its registration/login/refresh internals are not.
- **Asynchronous side-channel consumers** — `services/notification-service/`,
  `services/audit-service/`, `services/analytics-service/`, `services/report-service/`,
  `services/admin-service/`. They subscribe to the same SNS topic but are not on
  the synchronous user request path. They appear here only as gateway route
  entries (§3.1).
- **Deployment/platform** — `infrastructure/terraform/`, `demo-platform/`,
  Kubernetes manifests, CI.
- **Frontends as products.** `frontend/client-app` and `frontend/admin-dashboard`
  appear only as API consumers (§4.6).
- Route inventory and end-to-end narrative flows already documented in
  `docs/api-route-matrix.md` and `docs/flows.md` — cross-referenced, not duplicated.

---

## 2. Component map

| Component | Language / runtime | Entrypoint | Port |
| --- | --- | --- | --- |
| `services/api-gateway/` | Go 1.x, chi + `net/http/httputil` reverse proxy | `services/api-gateway/cmd/server/main.go` | 8080 |
| `services/file-service/` | Rust, Actix Web | `services/file-service/src/main.rs` | 8082 |
| `services/document-service/` | Python, FastAPI + async SQLAlchemy (uvicorn) | `services/document-service/app/main.py` | 8083 |
| `services/collab-service/` | Node/TypeScript, Express + Socket.IO + y-websocket | `services/collab-service/src/index.ts` | 8084 |
| `services/search-service/` | Python, **Flask** (gunicorn, 2 workers × 4 threads) | `services/search-service/app/main.py` | 8087 |
| `services/auth-service/` (dependency only) | Java, Spring Boot | `services/auth-service/src/main/java/com/otterworks/auth/AuthServiceApplication.java`; tokens in `.../security/JwtTokenProvider.java` | 8081 |
| `shared/openapi/` | OpenAPI 3.0.3 YAML | `shared/openapi/README.md` | — |
| `shared/events/` | JSON Schema draft-07 | `shared/events/schemas/*.json` | — |
| `shared/proto/` | protobuf, **aspirational** | `shared/proto/README.md` ("future migration path"; services communicate via REST/HTTP today) | — |
| `frontend/client-app/` | React + Vite (+ Capacitor) | `frontend/client-app/src/lib/api-client.ts` | 3000 |
| `frontend/admin-dashboard/` | SPA | `frontend/admin-dashboard/` | 4200 |

Infrastructure (`docker-compose.infra.yml`): PostgreSQL 15 (5432), Redis 7 (6379),
LocalStack 3.8 (4566 — S3/SQS/SNS/DynamoDB/SES/Cognito/Secrets Manager),
MeiliSearch v1.6 (7700).

Runtime images (from each `Dockerfile`): gateway `ENTRYPOINT /app/server`,
file-service `ENTRYPOINT /app/file-service`, document-service
`uvicorn app.main:app --host 0.0.0.0 --port 8083`, collab-service `node dist/index.js`,
search-service `gunicorn --bind 0.0.0.0:8087 --workers 2 --threads 4 "app.main:create_app()"`.

### Datastore ownership

| Service | Owns | Notes |
| --- | --- | --- |
| file-service | S3 bucket `otterworks-files`; DynamoDB tables `DYNAMODB_TABLE` (metadata), `DYNAMODB_FOLDERS_TABLE`, `DYNAMODB_VERSIONS_TABLE`, `DYNAMODB_SHARES_TABLE` | `services/file-service/src/config.rs`, `src/metadata.rs`, `src/storage.rs` |
| document-service | PostgreSQL tables `documents`, `document_versions`, `comments` | `services/document-service/app/models/document.py` |
| collab-service | Redis keys `doc:state:*`, `doc:snapshots:*`, `doc:meta:*` under prefix `collab:` | `services/collab-service/src/services/document-store.ts`, `src/config.ts` |
| search-service | MeiliSearch indexes `documents` and `files` | `services/search-service/app/services/meilisearch_client.py` (`FILES_INDEX`, `DOCUMENTS_INDEX`) |
| auth-service | PostgreSQL users/refresh tokens | outside scope; shares the same `otterworks` database as document-service (`docker-compose.yml`) |
| api-gateway | **nothing** — stateless except in-process rate-limit buckets and circuit-breaker state | `services/api-gateway/internal/middleware/ratelimit.go`, `internal/proxy/circuitbreaker.go` |

No service reads another service's datastore directly. Cross-service data movement is
either an HTTP call through/around the gateway or an SNS→SQS event (§3.3).

---

## 3. Architecture & data/control flow

### 3.1 Edge

`services/api-gateway/cmd/server/main.go` builds a single chi stack, in this order:

1. `RequestID`, `RealIP`
2. metrics middleware, structured (zerolog) request logger, `Recoverer`
3. `chimw.Compress(5)`
4. `middleware.NewRateLimiter(cfg.RateLimitRPS).Handler`
5. CORS
6. `middleware.JWTAuth{...}`
7. `/health`, `/metrics`, then the mounted proxy router

Server timeouts: `ReadTimeout 15s`, `WriteTimeout 30s`, `IdleTimeout 60s`
(`cmd/server/main.go`).

Route table — `ServiceRoutes()` in `services/api-gateway/internal/config/config.go`:

```
/api/v1/auth          -> AUTH_SERVICE_URL           /api/v1/search    -> SEARCH_SERVICE_URL
/api/v1/files         -> FILE_SERVICE_URL           /api/v1/analytics -> ANALYTICS_SERVICE_URL
/api/v1/folders       -> FILE_SERVICE_URL           /api/v1/admin     -> ADMIN_SERVICE_URL
/api/v1/documents     -> DOCUMENT_SERVICE_URL       /api/v1/audit     -> AUDIT_SERVICE_URL
/api/v1/templates     -> DOCUMENT_SERVICE_URL       /api/v1/reports   -> REPORT_SERVICE_URL
/api/v1/collab        -> COLLAB_SERVICE_URL         /api/v1/settings  -> AUTH_SERVICE_URL
/socket.io            -> COLLAB_SERVICE_URL
/api/v1/notifications -> NOTIFICATION_SERVICE_URL
/api/v1/preferences   -> NOTIFICATION_SERVICE_URL
```

`internal/proxy/router.go` uses `httputil.NewSingleHostReverseProxy` per prefix; the
target URL is host-only and the **full request path is preserved** (no prefix
stripping), so backends mount the same `/api/v1/...` paths the client used. Proxy
transport errors return `502`; circuit-breaker rejection returns `503`.

> Note: `docs/api-route-matrix.md` lists `/api/v1/folders`, `/api/v1/templates`,
> `/api/v1/preferences` and `/api/v1/reports` as *missing* gateway prefixes. As of the
> `config.go` read above, all four **are** present — that section of the matrix is stale.

### 3.2 Identity: established vs. merely trusted

This is the most important property of the subsystem and it is **not uniform**.

```
established once            forwarded as a bare header             re-established
┌──────────────┐  JWT   ┌──────────────┐   X-User-ID   ┌────────────────────────┐
│ auth-service │──────► │ api-gateway  │──────────────►│ file-service (trusts)  │
│ (HS256 mint) │        │ (verifies)   │               │ search-service(trusts) │
└──────────────┘        └──────┬───────┘               └────────────────────────┘
                               │ Authorization: Bearer … (passed through unchanged)
                               ▼
                        document-service / collab-service — verify the JWT themselves
```

- **Established** in `services/auth-service/.../security/JwtTokenProvider.java`:
  HMAC (`Keys.hmacShaKeyFor(jwt.secret)`), `sub` = user UUID, plus claims
  `email`, `name`, `roles`, `type: "access"`; `jwt.access-token-expiry` default
  **3600s**, refresh **2592000s** with `type: "refresh"` and a `jti`.
- **Verified** at the edge in `services/api-gateway/internal/middleware/jwt.go`:
  Bearer scheme only, HMAC signing method required, expiry checked.
  - exact public paths: `/api/v1/auth/login`, `/api/v1/auth/register`
  - public **prefixes**: `/health`, `/metrics`, **`/socket.io`**
  - `ProtectedPrefixPath` is set to the route prefixes from the table above, so a
    path not matching any prefix falls through unauthenticated to the 404 handler.
- **Forwarded** in `services/api-gateway/internal/proxy/router.go`: the director sets
  `X-User-ID` from `claims.Subject`, falling back to the custom `user_id` claim.
  The original `Authorization` header is passed through untouched.
- **Trusted, not verified**:
  - `services/file-service/src/handlers.rs` prefers `X-User-ID` for owner scoping and
    falls back to the multipart `owner_id` / query-string owner for direct callers.
  - `services/search-service/app/middleware/auth.py` accepts **either** the configured
    `SEARCH_SERVICE_TOKEN` as a bearer token **or** any non-empty `X-User-ID`.
- **Re-established downstream**:
  - `services/document-service/app/api/documents.py::_extract_user_id` decodes the
    bearer JWT with `JWT_SECRET` (`user_id` claim, else `sub`) and only falls back to
    `X-User-ID` when **no** `JWT_SECRET` is configured. Compose always sets one, so in
    the default local stack the header is ignored here.
    `_require_user_id` → 401; `_ensure_owner` → 403 on owner mismatch.
  - `services/collab-service/src/middleware/auth.ts` runs `jwt.verify` on the Socket.IO
    handshake token (`socket.handshake.auth.token` or `Authorization: Bearer`); the Yjs
    upgrade path in `src/index.ts` verifies a `token` query parameter or auth header.

Consequence: `X-User-ID` is a **trusted-network header**. Any caller that can reach
`file-service:8082` or `search-service:8087` directly (i.e. anything on the
`otterworks-network` Docker network, or a host with the published port) can assert an
arbitrary identity. The gateway overwrites the header for authenticated requests, so
it cannot be forged *through* the edge — except when the verified token carries neither
`sub` nor `user_id`, in which case the director sets nothing and a client-supplied
`X-User-ID` survives **(inference from the `if userID != ""` guard in `router.go`)**.

### 3.3 Upload → store → index → retrieve

```mermaid
sequenceDiagram
  autonumber
  participant UI as client-app (3000)
  participant GW as api-gateway (8080)
  participant FS as file-service (8082)
  participant S3 as LocalStack S3
  participant DDB as DynamoDB
  participant SNS as SNS otterworks-events
  participant SQS as SQS otterworks-search-events
  participant SS as search-service (8087)
  participant MS as MeiliSearch (7700)

  UI->>GW: POST /api/v1/files/upload (multipart, Bearer JWT)
  GW->>GW: verify HS256 JWT, extract sub
  GW->>FS: same path + X-User-ID: <sub>
  FS->>FS: read multipart fields file / owner_id / folder_id
  FS->>S3: put_object bucket=otterworks-files key=files/{owner}/{file_id}
  FS->>DDB: put metadata row + version row
  FS-)SNS: publish file_uploaded (errors ignored)
  FS-->>GW: 201 metadata
  GW-->>UI: 201
  SNS-)SQS: fan-out to otterworks-search-events
  SS->>SQS: long-poll receive
  SS->>SS: unwrap SNS envelope, normalize event shape
  SS->>MS: add/replace document in index "files"
  UI->>GW: GET /api/v1/search/?q=…  (X-User-ID scopes owner filter)
  GW->>SS: proxied
  SS->>MS: query
  UI->>GW: GET /api/v1/files/{id}/download
  GW->>FS: proxied
  FS-->>UI: presigned S3 URL (3600s TTL)
```

Step detail with sources:

1. **Upload** — `services/file-service/src/handlers.rs`. Multipart fields `file`,
   `owner_id`, `folder_id`. Owner = `X-User-ID` when parseable, else the multipart
   `owner_id`. Size cap `MAX_UPLOAD_BYTES`, default `104857600` (100 MiB),
   `services/file-service/src/config.rs`.
2. **Object write** — `services/file-service/src/storage.rs::put_object`, key
   `format!("files/{}/{}", owner, file_id)`. The S3 client is built with
   `AWS_ENDPOINT_URL` and **force-path-style** addressing so LocalStack works.
3. **Metadata write** — `services/file-service/src/metadata.rs` writes the file row and
   a version row into the respective DynamoDB tables.
4. **Event publish** — `services/file-service/src/events.rs` publishes to
   `SNS_TOPIC_ARN`. The handler discards the result (`let _ = events.file_uploaded(...)`),
   so a publish failure is invisible to the client and simply means the file is never
   indexed.
5. **Fan-out** — `scripts/localstack-init.sh` creates topic `otterworks-events`, queues
   `otterworks-search-events` / audit / notifications, and subscribes each queue to the
   topic.
6. **Index** — `services/search-service/app/services/sqs_consumer.py` runs a daemon
   long-poll thread (started from `app/main.py` when `SQS_ENABLED`), unwraps the SNS
   envelope, and `_normalize_event` reconciles three shapes (§4.3) into
   `{"action": ..., "data": ...}` for `app/services/indexer.py`.
7. **Query** — `services/search-service/app/api/search.py` scopes results by the
   `X-User-ID` header. Endpoints: `GET /api/v1/search/`, `GET /api/v1/search/suggest`,
   `POST /api/v1/search/advanced`, `GET /api/v1/search/analytics`.
8. **Retrieve** — `GET /api/v1/files/{id}` returns metadata;
   `GET /api/v1/files/{id}/download` returns a **presigned S3 URL valid 3600s**
   (`storage.rs::presigned_download_url`) rather than streaming bytes through the service.

The document path is the same shape with a different store: FastAPI writes to
PostgreSQL, then `services/document-service/app/services/event_publisher.py` publishes
a nested event to the same SNS topic; the search consumer normalizes it into the
`documents` index.

### 3.4 Realtime path

`services/collab-service/src/index.ts` runs three things on port 8084:

- Express HTTP: `/health`, `/metrics`, `GET /api/v1/collab/documents`,
  `GET /api/v1/collab/documents/:id/presence` — reachable via the gateway's
  `/api/v1/collab` prefix (so JWT-enforced at the edge).
- Socket.IO (`/socket.io`) with the JWT handshake middleware above.
- A `WebSocketServer` for non-Socket.IO upgrades running y-websocket, verifying the
  `token` query parameter / auth header before `setupWSConnection`.

State lives in Redis via `src/services/redis-adapter.ts` (key prefix `collab:`),
with `documentTtl` 86400s and `snapshotTtl` 604800s, max 50 snapshots per document
(`src/config.ts`, `src/services/document-store.ts`).

The browser connects **directly** to the collab service, not through the gateway:
`frontend/client-app/src/components/editor/collaborative-editor.tsx` uses
`VITE_COLLAB_WS_URL`, built as `ws://localhost:8084` in `docker-compose.yml`.

---

## 4. Key interfaces & contracts

### 4.1 JWT

Minted by `services/auth-service/src/main/java/com/otterworks/auth/security/JwtTokenProvider.java`:

```json
{ "sub": "<user uuid>", "email": "…", "name": "…", "roles": ["USER"],
  "type": "access", "iat": …, "exp": … }
```

Every data-plane service reads the same shared secret from the `JWT_SECRET`
environment variable (`docker-compose.yml` sets it for gateway, auth, file, document,
collab and search from `${JWT_SECRET:-otterworks-local-dev-jwt-secret-change-me-in-production}`).
The gateway's `JWTClaims` struct (`internal/middleware/jwt.go`) additionally understands
a non-standard `user_id` claim that the current auth-service does not emit.
collab-service also has `JWT_ISSUER` (default `otterworks-auth-service`) in
`src/config.ts`.

### 4.2 HTTP contracts

- `shared/openapi/document-service.yaml`, `shared/openapi/notification-service.yaml`,
  `shared/openapi/search-service.yaml` — the shared specs. The search spec documents
  the per-user scoping via `X-User-ID` explicitly and names **MeiliSearch** as the
  backing engine.
- `shared/openapi/README.md` — common models (`ErrorResponse` per RFC 7807,
  `PaginatedResponse`, `HealthResponse`, `AuditEvent`); each service also keeps its own
  spec in-tree. There is **no** shared spec for file-service or api-gateway.
- document-service serves a live spec at `/openapi.json` and Swagger UI at `/docs`
  (`services/document-service/app/main.py`).
- Route inventory per service: `docs/api-route-matrix.md`.

Document-service routes (`app/api/documents.py`, `comments.py`, `templates.py`):
`POST /api/v1/documents/`, `GET /api/v1/documents/`, `GET /api/v1/documents/search`,
`GET /api/v1/documents/exports`, `GET /api/v1/documents/shared`,
`GET|PUT|PATCH|DELETE /api/v1/documents/{document_id}`,
`GET /api/v1/documents/{document_id}/versions`, `.../versions/{id}/restore`,
`POST /api/v1/documents/{document_id}/share`, `GET .../export`,
`POST|GET|DELETE /api/v1/documents/{document_id}/comments[...]`,
`GET|POST /api/v1/templates`.

File-service routes (`services/file-service/src/main.rs`): `/api/v1/files/upload`,
`/api/v1/files`, `/api/v1/files/shared`, `/api/v1/files/trash`, `/api/v1/files/activity`,
`/api/v1/files/{id}` (+ `/download`, `/move`, `/rename`, `/versions`, `/trash`,
`/restore`, `/share`, share removal), and `/api/v1/folders` CRUD.

Search indexing routes (`services/search-service/app/api/index.py`):
`POST /api/v1/search/index/document`, `POST /api/v1/search/index/file`,
`DELETE /api/v1/search/index/<doc_type>/<doc_id>`, `POST /api/v1/search/reindex`.

Health/metrics: every service exposes `/health` and `/metrics`; search-service also has
`/health/ready`, which returns 503 with `{"reason": "meilisearch_unavailable"}`
(`app/api/health.py`). document-service `/health` reports
`checks.database = connected|disconnected` and degrades rather than failing
(`app/api/health.py`).

### 4.3 Event formats — three shapes for the same topic

`shared/events/schemas/` holds draft-07 JSON Schemas: `file-events.json`,
`document-events.json`, `collaboration-events.json`, `notification-events.json`,
`audit-events.json`. `file-events.json` defines `FileUploadedEvent` /
`FileSharedEvent` / `FileDeletedEvent` with flat camelCase keys
(`eventType`, `fileId`, `fileName`, `ownerId`, `folderId`, `mimeType`, `sizeBytes`,
`s3Key`, `timestamp`).

The producers do **not** agree:

| Producer | Shape | Source |
| --- | --- | --- |
| file-service | flat camelCase, matches `file-events.json` (`eventType`, `fileId`, `ownerId`, `folderId`, `mimeType`, `sizeBytes`) | `services/file-service/src/events.rs` |
| document-service | nested `{"event_type": …, "timestamp": …, "payload": {…}}` + SNS message attribute `event_type` — **does not** match `document-events.json`, which specifies flat `eventType`/`documentId` | `services/document-service/app/services/event_publisher.py` |
| direct HTTP indexing calls | `{"action": …, "data": {…}}` | `services/search-service/app/services/indexer.py::process_event` |

`sqs_consumer.py::_normalize_event` exists precisely to absorb all three. Event kinds
emitted by file-service: `file_uploaded`, `file_updated`, `file_deleted`, `file_shared`,
`file_trashed`, `file_restored`, `file_moved`.

`shared/proto/` is a placeholder: its README states services communicate via REST/HTTP
and the protobufs are a future gRPC migration path.

### 4.4 Environment variables (data plane only)

api-gateway (`internal/config/config.go`): `PORT` (8080), `JWT_SECRET` (**required** —
the process refuses to start without it), `RATE_LIMIT_RPS` (100),
`{AUTH,FILE,DOCUMENT,COLLAB,NOTIFICATION,SEARCH,ANALYTICS,ADMIN,AUDIT,REPORT}_SERVICE_URL`,
CORS settings, circuit-breaker `CB*` settings.

file-service (`src/config.rs`): `PORT` (8082), `S3_BUCKET` (`otterworks-files`),
`DYNAMODB_TABLE`, `DYNAMODB_FOLDERS_TABLE`, `DYNAMODB_VERSIONS_TABLE`,
`DYNAMODB_SHARES_TABLE`, `AWS_ENDPOINT_URL`, `SNS_TOPIC_ARN`, `MAX_UPLOAD_BYTES`,
`REDIS_HOST`/`REDIS_PORT`.

document-service (`app/config.py`, prefix `DOC_SVC_`): `DOC_SVC_DATABASE_URL`
(default `postgresql+asyncpg://otterworks:otterworks_dev@localhost:5432/otterworks`;
Compose points it at host `postgres`), `DOC_SVC_SNS_ENABLED`, `DOC_SVC_SNS_TOPIC_ARN`,
`DOC_SVC_AWS_ENDPOINT_URL`, pool and CORS settings; plus bare `JWT_SECRET` and
`SHARE_LINK_SALT` (`app/services/share_link.py`).

collab-service (`src/config.ts`): `HTTP_PORT` (8084), `REDIS_HOST`/`PORT`/`DB`/
`REDIS_KEY_PREFIX` (`collab:`), `JWT_SECRET`, `JWT_ISSUER`, `CORS_ORIGINS`,
`PERSIST_INTERVAL_MS` (30000), `SNAPSHOT_INTERVAL_MS` (300000), `DOC_TTL_SECONDS`,
`SNAPSHOT_TTL_SECONDS`, `MAX_SNAPSHOTS`.

search-service (`app/config.py`): `MEILISEARCH_URL` (Compose: `http://meilisearch:7700`),
index names (`documents`, `files`), `SQS_ENABLED` (Compose: `true`; code default false),
`SQS_QUEUE_URL` (`http://localstack:4566/000000000000/otterworks-search-events`),
`REQUIRE_AUTH` (default true), optional `SEARCH_SERVICE_TOKEN`.

All Compose services get `AWS_ACCESS_KEY_ID=test` / `AWS_SECRET_ACCESS_KEY=test` /
`AWS_ENDPOINT_URL=http://localstack:4566`, and every container runs `read_only: true`
with `no-new-privileges` and a `/tmp` tmpfs.

### 4.5 LocalStack resources

`scripts/localstack-init.sh` provisions: S3 buckets `otterworks-files`,
`otterworks-data-lake`, `otterworks-audit-archive`; SNS topic `otterworks-events`;
SQS queues for search / audit / notifications with subscriptions to that topic;
DynamoDB tables for file metadata, folders, versions, shares, audit, notifications and
preferences.

### 4.6 Frontends as consumers

`frontend/client-app/src/lib/api-client.ts`: axios instance, `baseURL` `/api/v1`
same-origin for web builds (Vite dev/preview proxy → `API_GATEWAY_URL`, default
`http://localhost:8080`, see `frontend/client-app/vite.config.ts`; nginx does the same
job in the image), or `VITE_API_BASE_URL` / `http://10.0.2.2:8080/api/v1` for Capacitor
native builds. It injects `Authorization: Bearer <localStorage otter_access_token>` and
converts snake_case response keys to camelCase.

Endpoints the client app calls (grep of `frontend/client-app/src`): `/auth/login`,
`/auth/register`, `/auth/logout`, `/auth/profile`, `/auth/users/lookup`,
`/auth/users/by-id/{id}`, `/files`, `/files/upload`, `/files/shared`, `/files/trash`,
`/files/activity`, `/files/{id}`, `/files/{id}/download`, `/files/{id}/rename`,
`/files/{id}/trash`, `/files/{id}/restore`, `/files/{id}/share`,
`/files/{id}/share/{userId}`, `/folders`, `/folders/{id}`, `/documents`,
`/documents/{id}`, `/documents/{id}/restore`, `/documents/{id}/share`, `/search`,
`/search/suggest`, `/notifications`, `/notifications/unread-count`,
`/notifications/{id}/read`, `/notifications/read-all`, `/settings`, plus
`/analytics/...` and `/billing/plans`. Realtime goes straight to `VITE_COLLAB_WS_URL`.

`frontend/admin-dashboard` targets the gateway via `API_URL` (Compose:
`http://localhost:8080`) and calls `/api/v1/admin/...` — the admin service, not the
data-plane services.

---

## 5. Operational runbook

### Bring the stack up

```bash
make infra-up      # docker compose -f docker-compose.infra.yml up -d
make up            # infra + app compose, --build
make up seed=1     # as above, then wait-for-db and run scripts/seed.py
make down
```

`make up` = `docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build`.
`make dev-backend` starts everything except the frontends. `make wait-for-db` polls
`docker exec otterworks-postgres pg_isready`. `make seed` runs `uv run scripts/seed.py`.

Published ports: gateway 8080, auth 8081, file 8082, document 8083, collab 8084,
notification 8086, search 8087, analytics 8088, admin 8089, audit 8090, report 8091,
client-app 3000, admin-dashboard 4200, Postgres 5432, Redis 6379, LocalStack 4566,
MeiliSearch 7700.

### Smoke-verify

```bash
curl -s localhost:8080/health
curl -s localhost:8082/health && curl -s localhost:8083/health
curl -s localhost:8084/health && curl -s localhost:8087/health/ready

# 401 without a token (JWT enforced at the edge)
curl -si localhost:8080/api/v1/files | head -1

TOKEN=$(curl -s -XPOST localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"…","password":"…"}' | jq -r .accessToken)

curl -s -H "Authorization: Bearer $TOKEN" -F file=@./README.md \
  localhost:8080/api/v1/files/upload
curl -s -H "Authorization: Bearer $TOKEN" 'localhost:8080/api/v1/search/?q=readme'

aws --endpoint-url=http://localhost:4566 s3 ls s3://otterworks-files --recursive
curl -s localhost:7700/indexes
```

The login response field name is not asserted here — check
`services/auth-service` DTOs before scripting against it.

### Build / test / lint

```bash
make build                 # docker compose build
make build-gateway         # go build -o bin/server ./cmd/server
make build-file            # cargo build --release
make build-collab          # npm run build  (tsc)
make test                  # every service's native test runner
make lint                  # every service's native linter
make test-api-flows        # UV_PROJECT_ENVIRONMENT=.venv uv run python -m pytest tests/api
```

Per-service equivalents from the `Makefile`, useful because the aggregate targets are
all-or-nothing:

| Service | test | lint |
| --- | --- | --- |
| api-gateway | `cd services/api-gateway && go test ./...` | `golangci-lint run` |
| file-service | `cd services/file-service && cargo test` | `cargo clippy -- -D warnings` |
| document-service | `cd services/document-service && pytest` | `ruff check .` |
| collab-service | `cd services/collab-service && npm test` | `npm run lint` |
| search-service | `cd services/search-service && pytest` | `ruff check .` |
| auth-service | `./gradlew test` | `./gradlew spotlessCheck` |

Verified while writing this document: `cd services/api-gateway && go test ./...` passes
(`internal/health`, `internal/middleware`, `internal/proxy` ok; `cmd/server` and
`internal/config` have no tests).

### Credentials / offline notes

- No real cloud credentials are needed locally: everything AWS-shaped is LocalStack with
  `AWS_ACCESS_KEY_ID=test`. `JWT_SECRET` has a local default in Compose and must be
  overridden anywhere real.
- `make test` / `make lint` require every toolchain on the host — Go, Rust, JDK+Gradle,
  Python, Node, sbt, Ruby/bundler, .NET. Both targets are sequential `&&`-less recipe
  lines, so a missing toolchain aborts the rest.
- First `make up` pulls images and compiles Rust/Java/Node from source; it is not an
  offline-friendly operation on a cold cache.
- `make test-api-flows` needs the stack already running on 8080.

---

## 6. Failure modes & gotchas

Observed in code/config, in rough order of blast radius:

1. **`make test` and `make lint` reference `frontend/web-app`, which does not exist.**
   The frontend directories are `frontend/client-app` and `frontend/admin-dashboard`.
   Both aggregate targets therefore fail at the "Web Frontend" step.
2. **No authorization checks on most file-service handlers.** `handlers.rs` uses
   `X-User-ID` for *scoping list queries* but the by-id paths (metadata, download,
   trash, delete, share) do not compare the caller against the stored owner. Any
   authenticated caller who knows a file UUID can act on it. Treat as intentional for
   this estate (it is a security-testing reference platform) — do not "fix" it here.
3. **Search index endpoints are edge-reachable and role-free.** `/api/v1/search/index/*`
   and `/api/v1/search/reindex` sit under the gateway's `/api/v1/search` prefix, and
   `app/middleware/auth.py` is satisfied by any non-empty `X-User-ID`. Any logged-in
   user can rewrite or wipe the index.
4. **`POST /api/v1/search/reindex` can empty the indexes.** `indexer.py` crawls the
   document and file services over HTTP and may clear/recreate indexes when the source
   fetch fails — a failed crawl looks like "search suddenly returns nothing".
5. **Upload succeeds even when the event fails.** `handlers.rs` does
   `let _ = events.file_uploaded(...)`. Symptom: the file downloads fine but never
   appears in search. Same story on the document side —
   `event_publisher.py` catches and logs SNS errors.
6. **Presigned download URLs embed the S3 endpoint the service knows.** With
   `AWS_ENDPOINT_URL=http://localstack:4566`, the URL handed to a browser contains the
   Docker-internal hostname `localstack`, which does not resolve on the host
   **(inference: the URL is generated by the SDK from the configured endpoint; not
   executed end-to-end while writing this)**.
7. **`/socket.io` is a public prefix at the gateway** (`DefaultPrefixPaths`), so the
   edge neither authenticates it nor injects `X-User-ID`; collab-service's own handshake
   verification is the only control on that path. Also, gateway `WriteTimeout` is 30s,
   which is hostile to long-lived proxied upgrades — **(inference)** one reason the
   client app connects directly to `ws://localhost:8084` instead.
8. **Two different identity sources in one hop.** document-service prefers the JWT and
   ignores `X-User-ID` when `JWT_SECRET` is set; file/search prefer `X-User-ID`. A token
   whose `sub` differs from the forwarded header produces different owners in different
   services. `docs/api-route-matrix.md` flags this as a thing tests should catch.
9. **Producer/schema drift.** document-service's nested `event_type`/`payload` envelope
   does not match `shared/events/schemas/document-events.json`. New consumers that trust
   the schemas will silently drop those events; only the search consumer's
   `_normalize_event` knows the real shape.
10. **Chaos hooks are live in normal builds.** Redis flags, checked per request:
    - `chaos:file-service:upload_s3_error` → uploads are redirected to the nonexistent
      bucket `otterworks-files-chaos-nonexistent` (`file-service/src/handlers.rs`)
    - `chaos:document-service:slow_queries` → 3–5s injected latency
      (`document-service/app/api/documents.py`)
    - `chaos:search-service:suggest_500` → `_rankingScore` lookup raises `KeyError`
      → 500 (`search-service/app/api/search.py`)
    Check these first when debugging a "flaky" local stack: `redis-cli keys 'chaos:*'`.
11. **Share links are unkeyed MD5.** `document-service/app/services/share_link.py` derives
    the token as `md5(f"{document_id}:{salt}")[:16]` with salt defaulting to
    `otterworks-share`. The docstring marks it as the OW-SEC-403 lab fixture — leave it.
12. **Route-shadowing risk in document-service.** `/documents/search`, `/documents/exports`
    and `/documents/shared` are declared before `/documents/{document_id}`; the ordering
    is what keeps them from being swallowed by the UUID path parameter.
13. **Gateway rate limiting is per-IP and in-process** (`internal/middleware/ratelimit.go`,
    100 RPS default, `Retry-After: 1`, buckets GC'd every 5 minutes after 10 idle
    minutes). Behind a shared egress IP it throttles everyone together, and it does not
    survive a restart or scale horizontally.
14. **document-service creates its schema at startup** via `init_db()` →
    `Base.metadata.create_all` (`app/db/session.py`, `app/main.py`) — no migration tool
    on this path, so column changes are not applied to an existing volume.
15. **Unmatched gateway paths are not authenticated**, they 404 — `ProtectedPrefixPath`
    is the route prefix list, so a typo'd prefix silently becomes a public 404 rather
    than a 401.
16. **`docs/api-route-matrix.md` is stale** on the four "missing prefix" gaps (§3.1).

---

## 7. Open questions / gaps

1. **OpenSearch vs MeiliSearch.** The task framing for this document referenced an
   OpenSearch dependency; the code and Compose files only contain MeiliSearch
   (`getmeili/meilisearch:v1.6`, `MEILISEARCH_URL`, `meilisearch.Client`), and
   `shared/openapi/search-service.yaml` says MeiliSearch too. The only OpenSearch
   references in the repo are in `demo-platform/docs/cost-and-scale.md`,
   `demo-platform/infra/terraform/budget.tf` and synthetic incident fixtures under
   `testdata/`. Whether a future migration to OpenSearch is planned is undocumented.
2. **Is `X-User-ID` trust intended as the permanent model**, or is it a stopgap until
   services verify JWTs themselves as document-service and collab-service already do?
   Nothing in-tree states the intended end state.
3. **No network policy documented** for the "trusted network" assumption. In Compose all
   services sit on `otterworks-network` and every port is published to the host, so the
   assumption does not hold locally.
4. **Nothing consumes `shared/proto/`.** No generated stubs or codegen step exists in the
   `Makefile`; is it still a live plan?
5. **`document-events.json` vs the actual publisher** (§4.3) — which is authoritative,
   and is any consumer other than search-service reading document events?
6. **Search reindex identity.** `indexer.py` calls the document/file services directly;
   which identity those calls carry, and whether they are meant to bypass the gateway,
   is not stated in code.
7. **Version/rollback semantics for files.** `storage.rs` uses `copy_object` for
   versioning and there is a versions DynamoDB table, but the retention policy and
   whether old S3 objects are ever reclaimed are undocumented.
8. **file-service has no shared OpenAPI spec** in `shared/openapi/` — intentional or an
   omission?
9. **Collab ↔ document persistence.** collab-service keeps Yjs state in Redis with a
   24h TTL and snapshots for 7 days; whether/how that state is ever flushed into
   document-service's PostgreSQL rows was not found in the code read for this document.
10. **`/api/v1/settings` routes to the auth service** in `config.ts`/`config.go` while the
    client app calls `/settings`; which service actually implements it was not verified.
