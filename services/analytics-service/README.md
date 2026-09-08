# Analytics Service

Scala 3 / Akka HTTP service that ingests platform events (via the REST API and
an SQS consumer) and serves aggregated analytics: dashboard summaries, per-user
activity, document stats, top content, active users, storage usage, and report
exports.

## Metrics store

Events and a daily aggregate rollup are persisted to a **durable PostgreSQL
store via Slick** — the golden-app default. The schema is applied with Flyway
from `src/main/resources/db/migration` (the same convention the JVM services in
this repo use):

- `analytics_events` — the raw event log (source of truth). The event instant is
  stored as epoch-nanoseconds (UTC) so it round-trips exactly regardless of DB
  timestamp precision or server time zone.
- `analytics_daily_metrics` — a materialized daily rollup (`event_date`,
  `event_type` → `event_count`) maintained transactionally on every write.

Query responses are derived from the durable event log via the pure,
storage-agnostic `MetricsAggregator`, which is shared with the in-memory backend
so both produce **byte-for-byte identical** results for the same event set.

### Backends

Selected by `analytics.repository.backend` (env `ANALYTICS_REPOSITORY_BACKEND`):

| value        | use                                                        |
|--------------|------------------------------------------------------------|
| `postgres`   | durable store (default; golden app)                        |
| `in-memory`  | ephemeral, process-local — for local runs and unit tests   |

The connection is assembled from `POSTGRES_*` (compose) unless `DATABASE_URL`
is provided explicitly (`scripts/deploy-dev.sh` wiring); `DATABASE_*` always
takes precedence. If the durable store cannot be initialised at startup, the
service logs a warning and falls back to the in-memory store so it still boots.

## Market data & margins (OTD-15)

The service also owns supply-chain market data and per-SKU margin analytics in a
dedicated **`analytics` schema** (its own Flyway history table
`flyway_schema_history_analytics`): `market_series`, `market_prices`, `products`,
`product_margin_daily`, `sync_runs`.

At startup an idempotent seeder loads the deterministic synthetic baseline
bundled from `testdata/market-series` (see the README there for the CSV
contract) and extends every series to "today" with a seeded random walk.

Endpoints (all behind the API-gateway JWT — no extra auth):

- `GET /api/v1/analytics/margins` — KPIs + per-SKU margin rows
- `GET /api/v1/analytics/margins/series?sku=|category=&from=&to=`
- `GET /api/v1/analytics/margins/export?format=csv`
- `GET /api/v1/analytics/market/series` / `market/prices?series_code=&from=&to=` / `market/status`
- `POST /api/v1/analytics/market/observations` — manual Trading Economics pulls:

```json
{
  "observations": [
    { "series_code": "SALMON_NOK_KG", "price_date": "2026-07-24", "value": 103.10 },
    { "series_code": "USD_NOK", "price_date": "2026-07-24", "value": 10.62 }
  ],
  "source_note": "tradingeconomics.com manual pull"
}
```

Each observation is validated (known series, ISO date not in the future,
positive value); valid ones upsert as `manual_pull` (winning over synthetic),
affected margins are recomputed synchronously and a `sync_runs` row is recorded.
Response reports `accepted`, itemized `rejected`, `recomputed_skus` and
`run_id`; an all-invalid request returns 400. There is **no** Trading Economics
API integration and no TE credentials — pulls are manual by design.

## Lakehouse migration — "before" state

This durable PostgreSQL store is the **"before"** state for a
REFACTOR / RE-ARCHITECT exercise that moves the analytics store to an
**S3 + Apache Iceberg lakehouse**. It is intentionally shaped so that migration
is a self-contained, verifiable step; the "after" is **not** built here.

### Target ("after") — outline only

- **Storage:** raw events land in S3 (partitioned by `event_date` /
  `event_type`) as an **Apache Iceberg** table; the daily rollup becomes an
  Iceberg aggregate table.
- **Catalog + query:** **AWS Glue Data Catalog** for table metadata and
  schema evolution; **Amazon Athena** (and/or Spark) for SQL over Iceberg.
- **Ingestion:** the existing SQS consumer writes to Iceberg (directly or via a
  streaming/compaction job) instead of `INSERT`-ing into PostgreSQL.
- **Serving:** the HTTP API and `DashboardSummary` semantics stay **identical**;
  only the repository implementation behind `MetricsRepository` changes.

### Continuous validation (reconciliation)

The migration is de-risked by a reconciliation check that asserts the
**old (PostgreSQL) and new (Iceberg) stores agree** for the same event set:

1. Seed / replay a fixed event set into both stores.
2. Compare every analytics response (`DashboardSummary`, `getUserActivity`,
   `getDocumentStats`, `getTopContent`, `getActiveUsers`, `getStorageUsage`,
   `getExportData`, event counts) field-for-field.
3. Cross-check the persisted daily rollup against counts derived from the raw
   event log.

The baseline for (2)–(3) already exists as
`src/test/scala/com/otterworks/analytics/repository/PostgresMetricsRepositorySpec.scala`,
which proves the durable PostgreSQL store reconciles exactly with the in-memory
store. The lakehouse "after" is expected to pass the **same** reconciliation
against this PostgreSQL "before", turning a one-off migration into a
continuously-validated cutover.

## Observability

Instrumentation mirrors `services/search-service` (Prometheus request metrics +
structured JSON logs) so the same dashboards, alerts and log queries apply.
Definitions live in `api/Metrics.scala` and `api/RequestInstrumentation.scala`.

### Prometheus metrics — `GET /metrics` (port 8088)

Exposed in Prometheus text format 0.0.4 from the default registry; this is what
the Helm chart's `ServiceMonitor` (`monitoring.path: /metrics`, port `http`) and
`observability/prometheus/prometheus.yml` (`analytics-service:8088`) scrape.

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `analytics_service_requests_total` | counter | `method`, `endpoint`, `status` | search-service equivalent: `search_service_requests_total` |
| `analytics_service_request_duration_seconds` | histogram | `method`, `endpoint` | search-service equivalent: `search_service_request_duration_seconds` |
| `analytics_service_requests_in_flight` | gauge | — | requests currently being handled |
| `analytics_service_events_received_total` | counter | `source` (`api`\|`sqs`), `event_type` | events accepted for storage |
| `analytics_service_sqs_messages_total` | counter | `outcome` (`processed`\|`decode_failed`\|`store_failed`\|`delete_failed`\|`receive_failed`) | SQS consumer health |
| `jvm_*`, `process_*` | various | — | JVM hotspot exports (`DefaultExports`) |

- `endpoint` is the **route template**, never the raw path (e.g.
  `/api/v1/analytics/users/{id}/activity`); unknown paths are labelled
  `unmatched`, so label cardinality stays bounded.
- Requests to `/health` and `/metrics` are **not** counted or logged (same as
  search-service), so probes and scrapes do not swamp real traffic.
- Responses produced by rejection/exception handling (404/405/500) are counted
  with their real status because the route tree is sealed inside the
  instrumentation.
- The previously declared but never-updated `analytics_events_received_total`,
  `analytics_request_duration_seconds` and `analytics_active_connections`
  families were replaced by the `analytics_service_*` names above.

### Structured JSON logs

All logs (application **and** Akka, via `akka-slf4j`) go through Logback's
`LogstashEncoder`, one JSON object per line. Every line carries the fields
required by `observability/logging/log-format-spec.md`: `timestamp`, `level`,
`service` (`analytics-service`), `message`, plus `logger` and `thread`.
Application messages are stable snake_case event names with the details as
top-level fields rather than interpolated into the message.

| `message` | Extra fields |
|---|---|
| `http_request_completed` (one per request) | `request_id`, `method`, `path`, `endpoint`, `status`, `duration_ms` |
| `event_tracked`, `event_accepted` | `event_id`, `event_type`, `user_id`, `resource_id`, `resource_type` (+ `source` on `event_accepted`) |
| `*_requested` (dashboard, user activity, document stats, top content, active users, storage, export) | `period`, `user_id`, `document_id`, `content_type`, `limit`, `format` as applicable (DEBUG) |
| `sqs_processor_starting`/`_started`, `sqs_event_processed`, `sqs_*_failed` | `queue` (name only, never the account URL), `region`, `event_id`, `event_type`, `error` + `stack_trace` |
| `metrics_store_selected`/`_fallback`, `market_seed_failed`, `server_started`/`_start_failed`, `sqs_processor_start_failed` | `store`, `requested_store`, `host`, `port`, `metrics_path`, `error` |

`request_id` is taken from an incoming `X-Request-ID` header (as set by the API
gateway) when it matches `[A-Za-z0-9._:-]{1,128}`, otherwise a UUID is generated;
it is echoed back on the response so a client-observed failure can be joined to
its log line.

### Verifying against a running tenant

Tenant `<ID>` runs in namespace `otterworks-<ID>`; the Helm release (and thus
the Service) is named `analytics-service`.

```bash
NS=otterworks-<ID>

# 1. Scrape endpoint the ServiceMonitor uses (pod port 8088, Service port 80)
kubectl -n "$NS" port-forward svc/analytics-service 8088:80 &
curl -s localhost:8088/metrics | grep -E '^analytics_service_|^# TYPE analytics_service_'

# 2. Generate traffic, then confirm counter/histogram moved and the endpoint is templated
curl -s -o /dev/null -w '%{http_code} %header{x-request-id}\n' \
  -H 'X-Request-ID: verify-1' localhost:8088/api/v1/analytics/users/u-1/activity
curl -s -X POST localhost:8088/api/v1/analytics/events -H 'Content-Type: application/json' \
  -d '{"eventType":"document.viewed","userId":"u-1","resourceId":"d-1","resourceType":"document"}'
curl -s localhost:8088/metrics | grep -E 'requests_total\{.*users/\{id\}/activity|events_received_total|request_duration_seconds_count'

# 3. Structured logs: one JSON line per request, joinable by request_id
kubectl -n "$NS" logs deploy/analytics-service --since=5m \
  | jq -c 'select(.message=="http_request_completed") | {request_id,method,endpoint,status,duration_ms}'
kubectl -n "$NS" logs deploy/analytics-service --since=5m | jq -c 'select(.request_id=="verify-1")'

# 4. ServiceMonitor is rendered and Prometheus has picked the target up
kubectl -n "$NS" get servicemonitor analytics-service -o jsonpath='{.spec.endpoints[0].path}{"\n"}'   # /metrics
# In the shared Prometheus UI/API:
#   analytics_service_requests_total{namespace="otterworks-<ID>"}
#   histogram_quantile(0.95, sum by (le, endpoint) (rate(analytics_service_request_duration_seconds_bucket{namespace="otterworks-<ID>"}[5m])))
```

`kubectl -n "$NS" logs deploy/analytics-service | grep '"message":"server_started"'`
shows the bind address and `metrics_path` at boot. Without the `monitoring.coreos.com`
CRDs installed the chart skips the ServiceMonitor; the static
`observability/prometheus/prometheus.yml` job covers that case.

## Build & test

```bash
sbt compile        # compile (the CI "lint" gate for this service — no scalafmt/scalafix configured)
sbt test           # unit tests + observability contract + durable-store reconciliation (Testcontainers)
sbt assembly       # fat jar (used by the Docker image / deploy)
```

`ObservabilitySpec` covers the `/metrics` contract, endpoint templating,
`/health`+`/metrics` exclusion, `X-Request-ID` propagation and the JSON request
log fields (rendered through the real `logback.xml` encoder).

The reconciliation suite uses Testcontainers and requires Docker; when Docker is
unavailable it is cancelled (not failed), so Docker-less runners stay green.
