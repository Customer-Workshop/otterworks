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
| `iceberg`    | S3 + Apache Iceberg via Glue/Athena (opt-in migration path) |
| `in-memory`  | ephemeral, process-local — for local runs and unit tests   |

The connection is assembled from `POSTGRES_*` (compose) unless `DATABASE_URL`
is provided explicitly (`scripts/deploy-dev.sh` wiring); `DATABASE_*` always
takes precedence. If the durable store cannot be initialised at startup, the
service logs a warning and falls back to the in-memory store so it still boots.

## Lakehouse migration (`ice1`)

PostgreSQL remains the default and durable **before** state. Setting
`ANALYTICS_REPOSITORY_BACKEND=iceberg` selects the sibling
`IcebergMetricsRepository`, which stores the canonical event log in the
`analytics_events_ice1` Iceberg table on S3 and materializes
`analytics_daily_metrics_ice1`. Glue supplies the catalog and Athena engine 3
performs Iceberg inserts, reads, and rollup `MERGE` operations.

All API responses still use `MetricsAggregator`; callers and routes are
unchanged. Athena rows use epoch-nanosecond timestamps and a monotonic ingest
sequence, preserving PostgreSQL timestamp and insertion-order semantics.

The namespaced Terraform module is
`module.analytics_iceberg_ice1`. It provisions the private/versioned S3 bucket,
Glue database, two Iceberg tables, Athena workgroup with CloudWatch metrics,
saved rollup/validation queries, and a least-privilege policy attached to the
analytics-service IRSA role.

### Continuous validation (reconciliation)

`IcebergReconciliationSpec` replays `usage-events.ndjson` into PostgreSQL and
the Iceberg row/schema stand-in, then uses `AnalyticsReconciler` to compare every
repository response field-for-field plus the persisted daily rollup. The same
adapter runs against Athena in deployment.

```bash
sbt "testOnly com.otterworks.analytics.repository.IcebergReconciliationSpec"

# Local gateway flow through the Iceberg adapter/schema seam
ANALYTICS_REPOSITORY_BACKEND=iceberg \
  docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build
make test-api-flows

# Namespaced AWS deployment
NAMESPACE=otterworks-ice1 ANALYTICS_REPOSITORY_BACKEND=iceberg \
  ./scripts/deploy-dev.sh --skip-platform
```

Revert:

```bash
cd infrastructure/terraform
terraform destroy -target=module.analytics_iceberg_ice1
# Redeploy with ANALYTICS_REPOSITORY_BACKEND unset (postgres default).
```

## Build & test

```bash
sbt compile        # compile
sbt test           # unit tests + durable-store reconciliation (Testcontainers)
sbt assembly       # fat jar (used by the Docker image / deploy)
```

The reconciliation suite uses Testcontainers and requires Docker; when Docker is
unavailable it is cancelled (not failed), so Docker-less runners stay green.
