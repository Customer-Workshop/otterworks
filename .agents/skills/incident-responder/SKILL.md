---
name: incident-responder
description: >
  Repo-specific mechanics for answering a production alert on OtterWorks
  document-service as the on-call first responder. Covers the four armable
  scenarios and what pages for each, the local Compose stack with Prometheus,
  Grafana, Jaeger and Alertmanager, the exact commands to reproduce an alert,
  read the trace and query fan-out, verify a fix with the before/after gate, and
  how the demo resets (disarm, revert, isolated tenant on the shared cluster).
---

# Incident Responder — OtterWorks

Repo-specific mechanics behind the `!incident_responder` Playbook. Auto-loaded
when Devin works in this repository. Everything below is document-service
(`services/document-service/`, Python 3.12, FastAPI, SQLAlchemy async, Alembic).

## The four scenarios on `main`

`main` deliberately ships four production flaws in document-service. They are the
durable before-state, they stay on `main`, and a fix lives on the responder's own
branch. `incident/scenarios.yaml` is the machine-readable source of truth
(what the user sees, what the chart shows, the code cause, the correct fix, the
load profile, the paging alert and its time-to-fire promise).

| Scenario | Paging alert (`page: devin`) | Fires within | Code cause | Fix shape |
|---|---|---|---|---|
| `n-plus-one` | `DocumentListLatencyHigh` (p95 of `GET /api/v1/documents/` > 1 s for 1 m) | 180 s | `app/services/document_service.py` `DocumentService.list_documents` runs one `document_versions` SELECT per document; no index on `documents(owner_id, is_deleted, is_template, updated_at)` or `document_versions(document_id, version_number)` | one batched versions query, one Alembic migration adding both indexes, one test pinning the query count |
| `log-flood` | `RequestLogVolumeNearFull` (request-log bytes / capacity > 0.80 for 30 s) | 240 s | `app/middleware/request_log.py` appends every response body to one JSONL file, no cap, no rotation, raises on write failure | bounded rotation, logging failure never fails the request, test that writes past the cap |
| `cache-leak` | `DocumentServiceMemoryHigh` (RSS / memory limit > 0.75 for 1 m) | 420 s | `app/services/render_cache.py` is a plain dict keyed by (document, version, format) with no eviction | bounded LRU or TTL, test that inserts past the bound |
| `double-run` | `DocumentStatsRollupDuplicated` (`otterworks_rollup_duplicate_windows` > 0) | 240 s | `app/jobs/stats_rollup.py` schedules the rollup in every process with no lock; two replicas insert the same window | PostgreSQL advisory lock or unique `window_start` + `ON CONFLICT DO NOTHING`, test running two rollups for one window |

`n-plus-one` is the flaw the code was shipped with — it is on regardless of any
flag. The other three are gated behind Redis chaos flags
(`app/chaos.py`: `chaos:document-service:{request_log,render_cache}`) or a second
replica, so they are off until armed and fail closed when Redis is unreachable.
`DocumentListQueryFanout` (SQL statements per request > 20) is diagnostic: it
fires alongside `DocumentListLatencyHigh` but does not page.

The armed `log-flood` request log is the flaw, not a feature: it records
response bodies (with credential headers, bearer-like query parameters and
token fields redacted) into a tmpfs on the Compose stack, or the container's
ephemeral filesystem on the isolated tenant's pod, over seeded demo data only.
`make disarm` purges it and the tenant is disposable, so nothing outlives the
run. A real remediation removes body capture or restricts it to a bounded,
access-controlled store — do not turn the flag on against `otterworks-main` or
any tenant holding real data.

Two things that are *not* in scope: `services/admin-service/config/environments/production.rb`
(a different planted bug, see `AGENTS.md`) and anything under `security/`
(other exercises). Do not "fix" the flaw on `main`; work on your own branch.

## Commands

```bash
make incident-up                              # document-service + Postgres/Redis + Prometheus/Grafana/Jaeger/Alertmanager
make incident-up UI=1                         # also api-gateway + web-app so the slowness shows in a browser
make arm SCENARIO=n-plus-one                  # plant the flaw, seed the dataset, start deterministic load
make incident-status                          # firing page=devin alerts and the numbers behind them
make incident-verify SCENARIO=n-plus-one EXPECT=before   # gate: fixture pinned, alert fired in time, before-thresholds met, webhook captured
make incident-verify SCENARIO=n-plus-one EXPECT=after    # gate: source changed, same load, alert clears, after-thresholds met
make incident-simulate RECEIVER=devin         # the exact JSON the Devin Automation webhook received
make incident-load SCENARIO=n-plus-one DURATION=120      # the load profile in the foreground (prints p50/p95/queries per request)
make disarm                                   # stop load, clear flags, restore replicas/logs
make incident-fingerprint                     # fixture/source fingerprints vs incident/expected.yaml
make incident-record REASON="..."             # re-pin incident/expected.yaml (audited; the reason is committed)
make incident-down                            # stop the stack (volumes kept)
```

`make arm` / `make disarm` are aliases for `make incident-arm` / `make incident-disarm`.
The harness is `incident/incident.py` (run under `uv`, no install step). Its
`verify` exits `0` green, `1` red, and always writes
`incident/reports/<scenario>-<before|after>-<stamp>.json` — on red as well as
green. The reports directory is git-ignored generated output; paste the summary
lines into the PR body rather than committing them.

Ports (Compose, all loopback): document-service `8083`, Postgres `5432`, Redis
`6379`, Prometheus `9090`, Grafana `3001` (`admin` / `otterworks`), Jaeger
`16686`, Alertmanager `9093`, alert sink `9095`, OTLP collector `4318`.
With `UI=1`: api-gateway `8080`, web-app `3000`. Override targets with
`INCIDENT_BASE_URL`, `INCIDENT_PROM_URL`, `INCIDENT_COMPOSE`; `INCIDENT_LOAD_SCALE`
(default `1`) multiplies a scenario's rps and concurrency for a target with less
headroom than the local stack (the local gates always run unscaled).

The fixture dataset is deterministic (`incident/scenarios.yaml` → `seed`): one
owner `6d0c5f5e-7f0f-4a4e-9d0c-1a1c1d3a7000`, 400 documents, 8 versions each,
seeded from `random_seed: 20260924`. Seeding is idempotent on (owner, title).
The load generator signs its own JWT with the Compose `JWT_SECRET`; requests
carry `X-DB-Queries` (SQL statements issued for that request) and
`X-Request-Duration-Ms` response headers, so a single `curl -i` already shows
the fan-out.

## Read telemetry first

Everything document-service exports is in `app/telemetry.py`:
`http_requests_total`, `http_request_duration_seconds` (by `handler`, `method`,
`status`), `otterworks_db_queries_per_request` (histogram by `handler`),
`otterworks_db_query_duration_seconds`, `otterworks_process_resident_memory_bytes`
and `otterworks_process_memory_limit_bytes`, `otterworks_request_log_bytes` and
`otterworks_request_log_capacity_bytes`, `otterworks_render_cache_entries`,
`otterworks_rollup_runs_total` and `otterworks_rollup_duplicate_windows`.

```bash
# the page you were handed
make incident-simulate RECEIVER=devin | jq '.payload.alerts[0] | {labels, annotations, startsAt}'

# p95 and statements per request for the list endpoint, right now
curl -s 'localhost:9090/api/v1/query' --data-urlencode \
  'query=histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="document-service",handler="/api/v1/documents/",method="GET"}[2m])))' | jq '.data.result[0].value[1]'
curl -s 'localhost:9090/api/v1/query' --data-urlencode \
  'query=sum(rate(otterworks_db_queries_per_request_sum{handler="/api/v1/documents/"}[2m])) / sum(rate(otterworks_db_queries_per_request_count{handler="/api/v1/documents/"}[2m]))' | jq '.data.result[0].value[1]'

# one slow trace and the SQL spans inside it
curl -s 'localhost:16686/api/traces?service=document-service&operation=GET%20/api/v1/documents/&minDuration=1s&limit=1' \
  | jq '.data[0].spans | map(select(.operationName|startswith("SELECT"))) | length, (.[0].tags[]|select(.key=="db.statement")|.value)'
```

Grafana dashboard: `http://localhost:3001/d/otterworks-incident-responder`
(`observability/grafana/dashboards/incident-responder.json`). The three panels a
reviewer wants to see are request rate (flat), p95 latency (climbing) and SQL
statements per request (stepping from 4 to 104 for a 100-row page; a batched fix
lands at 5, which is the after gate's ceiling). Alert rules
are in `observability/prometheus/incident_alerts.yml`; routing (`page: devin` →
Devin webhook and Slack, everything else → local sink) is in
`observability/alertmanager/alertmanager.yml.tmpl`.

## Reproduce, fix, prove

```bash
make incident-up && make arm SCENARIO=n-plus-one
make incident-verify SCENARIO=n-plus-one EXPECT=before      # red until the alert fires, then green: this is the reproduction
# ... change app/, add alembic/versions/004_*.py, add a test ...
cd services/document-service && poetry install --no-interaction && poetry run ruff check . && poetry run pytest -q tests/test_telemetry.py tests/test_document_service.py
cd ../.. && docker compose -f docker-compose.yml -f docker-compose.infra.yml -f docker-compose.incident.yml up -d --build document-service
make incident-verify SCENARIO=n-plus-one EXPECT=after       # drives the same load for 150 s (SOAK=<s> to change), alert must clear
```

The `after` gate refuses to run against an unchanged source fingerprint, so it
cannot be passed by waiting for the load to stop — and it requires the scenario
to **still be armed**: do not `make disarm` before `EXPECT=after`. It re-applies
the scenario's own conditions (`after_prepare` in `incident/scenarios.yaml`:
purge the request log, recreate the service under the 256m ceiling, restart the
replica on the rebuilt image), checks they hold, drives the same load profile
(or lets the replicas run) for `after_soak_seconds`, then requires the alert
inactive **and** the scenario's `after:` thresholds met (`queries_per_request`
and `p95_seconds` for n-plus-one, `request_log_ratio`, `cache_entries` /
`memory_ratio`, new rollup windows with zero duplicates from the table and the
gauge). Rebuild the image before the `after` run — verifying against the old
container is the most common way to get a meaningless green. Migrations run on
container start (`app/db/migrate.py`), so a new `alembic/versions/004_*.py` is
applied by the rebuild.

The gates never read `nan` as a number. A threshold whose metric has no samples
in the 2 m window fails with `no samples in the 2m window (Prometheus returned
nan/none)`, and the `after` gate additionally requires the offered load to have
reached the service: `request_rate >= 12 rps` (half the pinned 24 rps profile).
Both are diagnostics about the environment, not verdicts on the fix: the load
generator prints `shed=N` when its 24 concurrent slots are all busy, and a host
that sheds most requests after the fix is too small for the unscaled profile
(the local Compose stack with Prometheus, Grafana, Jaeger, Postgres and the
service was verified green on 8 vCPU / 32 GB; on a 2-4 vCPU laptop expect the
before gate to pass and the after gate to trip the load-reached check). Do not
lower the profile or `INCIDENT_LOAD_SCALE` to make the gate pass — the verify
command ignores the scale on purpose — move to a bigger host or the isolated
tenant below and quote that in the PR.

Nine pre-existing failures in `tests/test_documents_api.py` (mutating endpoints
called without an auth header, asserting `200` against a `401`) and
`test_restore_version` are on `main` and are **not** yours to fix; run the
focused files above, and report the full-suite count as "9 failed on `main`,
N failed on the branch" if you run it.

Before/after numbers for the PR body come from the two report files
(`metrics.p95_seconds`, `metrics.queries_per_request`) or from
`make incident-load SCENARIO=n-plus-one DURATION=60` on each build.

## The page and the automation

Alertmanager always posts the firing alert to the local sink
(`http://alert-sink:9095/devin`) and, when `DEVIN_WEBHOOK_URL` +
`DEVIN_WEBHOOK_SECRET` are set, also to the Devin Automation webhook trigger
(with `X-Webhook-Secret`); when `SLACK_WEBHOOK_URL` is set it posts to
`#otterworks-alerts` too, otherwise to the sink's `/slack`. So the flow runs
with no external credentials, and in real mode the before gate and
`make incident-simulate` (which prints exactly what the Automation received)
still read the mirrored copy. The sink is an intentionally
unauthenticated, disposable capture buffer: it is reachable only on the Compose
network and on the host's loopback (`127.0.0.1:9095`), and must never be
published beyond the laptop — a real deployment posts to the Devin Automation
webhook and Slack directly. The Automation's trigger, prompt,
connectors, ACU budget and network policy are documented in
`docs/incident-responder/automation.md`; the prompt tells the session to post
the RCA as a reply in the alert's Slack thread (`channel` and `ts` are in the
Slack payload) before opening the PR.

## On the shared EKS cluster

The local Compose stack is the default and is all a laptop needs. To show the
same alert on a real tenant, deploy an isolated one from `main` and inject
there — never on `otterworks-main` / `t-main.otterworks.app` (see `AGENTS.md`).
Branch tenants live under `demo.otterworks.app`; only the perpetual `main`
tenant sits at `otterworks.app`. The tenant id is `incident` (branch
`demo-incident`, namespace `otterworks-incident`):

```bash
scripts/deploy-tenant.sh incident --profile core --host-suffix demo.otterworks.app --ttl 8h --branch demo-incident
INCIDENT_BASE_URL=https://api-t-incident.demo.otterworks.app make incident-seed
INCIDENT_BASE_URL=https://api-t-incident.demo.otterworks.app make incident-load SCENARIO=n-plus-one DURATION=300
scripts/teardown-tenant.sh incident
```

Cluster-wide Prometheus/Grafana/Jaeger are platform infrastructure (the
`platform-engineering-shared-services` repo), not this one; the document-service
Helm chart only needs its `ServiceMonitor` enabled to be scraped there. Pushing
to a `demo-<id>` branch ships it to that tenant via `.github/workflows/cd-tenant.yml`
(72 h TTL), which is how a merged fix reaches the sandbox during the demo.

## Reset and revert

- `make disarm` stops the load, clears chaos flags, purges the request log,
  removes the second replica and restarts document-service. It does not touch
  the database fixture (idempotent seed) or the PR.
- To reset after a fix was merged into a demo tenant branch:
  `git revert <merge-sha>` on that branch (or redeploy the golden image with
  `scripts/deploy-tenant.sh incident --image-tag <golden>`), then
  `make arm SCENARIO=...` again. Locally, `git checkout main -- services/document-service`
  and `make incident-up` rebuilds the before-state image.
- If the fix carried a migration (the reference fix adds `004_document_list_indexes`),
  downgrade the database **before** rebuilding the before-state image, while the
  fix's code is still present: `docker compose -f docker-compose.yml
  -f docker-compose.infra.yml -f docker-compose.incident.yml exec -T -w /app
  document-service sh -c 'PYTHONPATH=/app alembic downgrade 003'`. Otherwise the
  before-state container exits with `Can't locate revision identified by '004'`
  at boot because the database is stamped past the revisions it ships.
- `make incident-verify SCENARIO=<name> EXPECT=before` must go green again
  after any reset; if it reports fixture drift, something other than the fix
  changed and the recorded evidence (`incident/expected.yaml`) explains what is
  pinned.
