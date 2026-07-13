# Nightly Usage-Rollup Batch Job

> **Status: LEGACY "before" state.** This is a deliberately batch, timer-driven,
> poll-and-process job. It exists so a **batch → event-driven re-architecture**
> demo has a realistic starting point to convert. The event-driven "after"
> (EventBridge → SQS → Lambda) is intentionally **not** implemented here.

## What it is

`analytics-service` ingests raw analytics events (document views, file uploads,
storage allocations, collaboration sessions, etc.). The **nightly usage-rollup
job** is the classic legacy reporting pattern layered on top of that stream:

1. **Wake up on a fixed schedule** — a Kubernetes `CronJob` fires nightly
   (`0 2 * * *` UTC).
2. **Bulk-load ALL of the day's events synchronously** (poll-and-process). The
   whole batch is read into memory up front — there is no per-event trigger.
3. **Aggregate in a single pass** into one `DailyUsageRollup` per calendar day
   (UTC): total events, distinct active users, per-type counts, and storage
   allocated / released / net bytes.
4. **Write one output document** (`UsageRollupReport`) and exit.

This is intentionally **not** event-driven: nothing reacts to individual events;
work is deferred to a nightly window and processed in one large synchronous
sweep. That latency + batch-window coupling is exactly what the re-architecture
demo removes.

### Code

| Concern | File |
|---------|------|
| Batch entrypoint (main) | `services/analytics-service/.../batch/UsageRollupJob.scala` |
| Pure aggregation logic | `services/analytics-service/.../batch/UsageRollupAggregator.scala` |
| Bulk NDJSON loader | `services/analytics-service/.../batch/EventLoader.scala` |
| Output models | `services/analytics-service/.../model/UsageRollup.scala` |
| Deterministic seed data | `services/analytics-service/src/main/resources/seed/usage-events.ndjson` |
| Seed generator | `services/analytics-service/scripts/generate_seed_events.py` |
| Unit tests | `services/analytics-service/src/test/.../batch/*.scala` |
| Kubernetes CronJob | `infrastructure/helm/analytics-service/templates/cronjob.yaml` |

## Run it locally

```bash
# From repo root — runs against the bundled deterministic seed, writes
# rollup-output.json (override the path with OUT=...).
make batch-usage-rollup
# or:
scripts/run-usage-rollup.sh /tmp/usage-rollup.json

# Regenerate the deterministic seed (reproducible byte-for-byte):
make batch-usage-rollup-seed
```

Configuration is via environment variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `ROLLUP_INPUT` | `/seed/usage-events.ndjson` | NDJSON events source: a filesystem path, else a classpath resource |
| `ROLLUP_OUTPUT` | `rollup-output.json` | Output JSON path |

Against the bundled seed (165 events across 2024-03-01…03), the job produces
three identical daily rollups (55 events/day, 8 active users, 6 MiB allocated /
2 MiB released / 4 MiB net) — deterministic output suitable for assertions.

## Deployment

The job ships as a `CronJob` in the `analytics-service` Helm chart
(`cronjob.enabled: true`), reusing the service image, ServiceAccount (IRSA), and
`envFrom` config/secret wiring. It overrides the container entrypoint to run
`com.otterworks.analytics.batch.UsageRollupJob`.

```bash
helm template analytics-service infrastructure/helm/analytics-service \
  --set image.tag=<tag> --show-only templates/cronjob.yaml
```

## The re-architecture demo this enables (the "after" — NOT built here)

The batch job couples reporting to a nightly window and reprocesses everything
in bulk. The target is a low-latency, event-driven pipeline:

```
                 (today: batch)                         (target: event-driven)

  analytics events                              analytics event
        │                                              │  emits domain event
        ▼                                              ▼
  [ nightly CronJob ]                          [ Amazon EventBridge rule ]
        │  bulk read all events                       │  routes matching events
        ▼                                              ▼
  aggregate in one pass                        [ Amazon SQS queue ]  (buffer/retry/DLQ)
        │                                              │  triggers
        ▼                                              ▼
  write daily rollup                           [ AWS Lambda ]  incremental rollup upsert
                                                       │
                                                       ▼
                                               rollups updated continuously
```

Conversion sketch (out of scope for this PR):

- **Producer** — services publish domain events to **EventBridge** (or reuse the
  existing SNS topic) instead of the rollup reading them nightly.
- **EventBridge rule** — pattern-matches usage events and forwards them to an
  **SQS** queue (buffering, retries, dead-letter queue).
- **Lambda** — consumes SQS in small batches and performs an **incremental**
  rollup upsert (e.g. `date` partition in DynamoDB/Postgres), so rollups are
  fresh within seconds instead of up to 24 h stale.
- **Decommission** the CronJob once the event path is validated.

`UsageRollupAggregator` is deliberately pure and I/O-free, so the same
aggregation semantics can be reused by the Lambda handler when the "after" is
built.
