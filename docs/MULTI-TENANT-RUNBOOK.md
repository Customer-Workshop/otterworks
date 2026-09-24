# OtterWorks Multi-Tenant Demo — Operator Runbook

Execution of `docs/MULTI-TENANT-DEMO-PLAN.md`. Stands up many **isolated,
ephemeral** copies of the golden app on the **shared** `otterworks-dev` EKS
cluster, one per attendee/demo run (`ATTENDEE_ID` → namespace
`otterworks-<ATTENDEE_ID>`).

> The golden app is `main`. Tenants are derived from it; variants/bugs are
> injected per tenant and **never** flow back into `main`
> (see `AGENTS.md`).

## Scripts

| Script | Purpose |
|---|---|
| `scripts/tenant-platform-baseline.sh` | **Run once.** Installs the SHARED ingress-nginx (one NLB) and the namespace TTL reaper CronJob. |
| `scripts/deploy-tenant.sh <ID> [--tier A\|B] [--image-tag TAG] [--ttl 8h] [--host-suffix DOMAIN]` | Deploy/redeploy one tenant (applies `infrastructure/helm/tenant-values/<ID>/` overlays). |
| `scripts/teardown-tenant.sh <ID> [--keep-db] [--keep-trust]` | Delete one tenant (namespace + per-tenant DB + IRSA trust). |
| `scripts/inject-bug.sh <ID> <list\|reset\|scenario>` | Inject/clear a per-tenant bug (chaos flag / config / image). |
| `scripts/tenant-scale.sh <ID> <up\|down>` | Scale a tenant's compute to zero (or back) between sessions. |
| `scripts/bug-catalog.yaml` | The demo-scenario → variant registry. |
| `scripts/lib/tenant-common.sh` | Shared library (naming, TF-output loading, per-service Helm wiring). |

## Prerequisites (per shell)

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=us-east-1
# aws sts get-caller-identity  -> expect the workshop account (<AWS_ACCOUNT_ID>) and a Devin-PartnerWorkshops-Internal IAM identity
export DB_PASSWORD='<shared RDS master password>'
# Stable across redeploys so issued JWTs / Rails sessions stay valid:
export JWT_SECRET='<hex>' SECRET_KEY_BASE='<hex>'
```

Env vars do not persist between separate shell commands in some runners —
re-export within each command or combine into one.

## First-time setup

```bash
./scripts/tenant-platform-baseline.sh          # shared ingress + reaper (once)
```

## Spin up two tenants

```bash
./scripts/deploy-tenant.sh a01 --ttl 8h
./scripts/deploy-tenant.sh a02 --ttl 8h
kubectl get ns -l app.kubernetes.io/managed-by=otterworks-tenant
```

Reach a tenant's API without DNS:

```bash
kubectl -n otterworks-a01 port-forward svc/api-gateway 8080:8080
curl -s localhost:8080/api/v1/... 
```

With wildcard DNS, pass `--host-suffix demo.example.com` → the tenant is served
at `t-a01.demo.example.com` (web) and `api-t-a01.demo.example.com` (gateway)
through the one shared ingress/NLB.

## Isolation model (what is shared vs. per-tenant)

| Concern | Per-tenant mechanism |
|---|---|
| Compute | namespace + `ResourceQuota` + `LimitRange` + `NetworkPolicy`, `replicas=1` |
| Chaos flags / sessions / collab | **per-tenant in-cluster Redis** (`redis.<ns>`) — chaos keys are un-prefixed, so a shared Redis would leak bug injection across tenants; a dedicated Redis fully isolates it |
| Search | **per-tenant in-cluster MeiliSearch** |
| Relational data | **per-tenant RDS database** `otterworks_<ID>` on the shared instance (auth-service Flyway + document-service `create_all` self-provision the schema on boot) |
| Object storage | shared `otterworks-files-dev` bucket (objects keyed by UUID); listing is driven by the per-tenant DB / DynamoDB, so no cross-tenant listing |
| DynamoDB / S3 access | shared per-service **IRSA roles**; `deploy-tenant.sh` extends each role's trust policy to the tenant namespace's service accounts (dev-reuse model; the Terraform `modules/irsa` change makes this the reproducible default) |

**Tier A (default, implemented):** shared physical stores, isolated logically as
above. Blast radius: the shared S3 bucket and DynamoDB dev tables are physically
shared (mitigated because listings come from the per-tenant DB and objects use
UUID keys). Redis, MeiliSearch and the relational DB are fully per-tenant.

**Tier B (data-isolated):** additionally provision per-tenant DynamoDB tables and
scoped IRSA. **Not enabled by default** because the shared file-service IAM
policy is pinned to the `*-dev` table ARNs; enabling Tier B requires broadening
that policy resource to `otterworks-*` (or minting per-tenant roles) — see
"Known limitations". The per-tenant RDS database already gives Tier-B-grade
isolation for all Postgres-backed services today.

## Bug injection (per tenant, never touches others)

```bash
./scripts/inject-bug.sh a01 list
./scripts/inject-bug.sh a01 file-upload-fails     # chaos flag in a01's Redis only
./scripts/inject-bug.sh a01 reset                 # clear a01's chaos flags
```

Mechanisms: `chaos` (Redis flag, instant, auto-expiring), `config` (helm upgrade
+ rollout restart), `image` (variant image tag for one service). Fixing a bug
mid-demo is the same lever scoped to the one namespace (seconds).

## Cost controls

- One shared EKS cluster + node group; `replicas=1` per tenant; `ResourceQuota`
  caps each tenant (4 CPU / 8Gi requests, 40 pods).
- One shared ingress/NLB for all tenants (no per-tenant ELB).
- **Scale-to-zero** idle tenants: `./scripts/tenant-scale.sh <ID> down`.
- **TTL reaper** CronJob (every 15m) deletes tenant namespaces whose
  `demo/expires-at-epoch` annotation is in the past (integer compare only, so the
  reaper image needs nothing more than `date +%s`).
- Tenants reuse the golden ECR image tags; only variants build new images.

## Teardown

```bash
./scripts/teardown-tenant.sh a01     # drops ns + per-tenant DB + IRSA trust subs
```

## Verified live (2026-07-13, cluster `otterworks-dev`)

Stood up `a01` + `a02` concurrently on the shared cluster and confirmed:

- **Separate namespaces**, each 12/13 pods Running (`admin-service` crash-loops by
  design). Every tenant Service is `ClusterIP` — **no per-tenant LoadBalancer**;
  the only ELBs are the one shared `ingress-nginx` NLB and the golden app's.
- **Shared ingress routing:** `curl -H "Host: api-t-a01..." $NLB/health` → 200 and
  the same for `a02`; web hosts `t-a01/t-a02` → 200; unknown host → 404 — all
  through the single NLB.
- **Relational isolation:** a user registered in `a01` (`201`, login `200`) does
  **not** exist in `a02` (login `400`); re-registering the same email in `a02`
  succeeds (`201`) — proving independent per-tenant databases.
- **Bug isolation:** injecting `search-suggest-500` into `a01` only → `a01`
  `/search/suggest` returns `500` while `a02` stays `200`; `reset` restores `a01`.
- **Cost controls:** `tenant-scale.sh a02 down` → 15/15 deployments at 0 replicas
  (0 running pods), `up` restores them; the reaper kept both live tenants and
  deleted a synthetic expired namespace.
- **Teardown/cleanup:** both tenants removed — namespaces gone, per-tenant DBs
  dropped, and tenant subjects removed from the shared IRSA role trust policies.

Note: the 2-node SPOT group is sized for the golden app; running two extra full
tenants required scaling the shared node group to 4 (`t3.large` SPOT). Size the
shared group for the expected number of concurrent tenants (or enable an
autoscaler) rather than per-tenant node groups.

## Per-tenant Helm values

`scripts/deploy-tenant.sh <ID>` passes `infrastructure/helm/tenant-values/<ID>/<service>.yaml`
to that service's `helm upgrade --install` with `-f` when the file exists. The
same script runs under CD and by hand, so an overlay committed on a tenant's
branch applies to every deploy of that tenant and to no other.

## Incident-response tenant (`demo-incident` → `incident`)

The branch `demo-incident` owns tenant id `incident` (`branch_tenant_id` strips
`demo-`): namespace `otterworks-incident`, hosts `t-incident.demo.otterworks.app` /
`api-t-incident.demo.otterworks.app` (the branch-tenant suffix external-dns
manages; only the perpetual `main` tenant answers at `otterworks.app`), image
tag `tenant-incident`, 72 h TTL. Its
overlay `infrastructure/helm/tenant-values/incident/document-service.yaml`
turns on the document-service chart's opt-in observability:

| Values key | Renders | Requires |
|---|---|---|
| `monitoring.enabled` | `ServiceMonitor` (named port `http`, `/metrics`, label `release: prometheus`) | `monitoring.coreos.com/v1` API |
| `monitoring.rules.enabled` | `PrometheusRule` from `files/incident_alerts.yml`, every expression scoped to `namespace="<release ns>"` | `monitoring.coreos.com/v1` API |
| `monitoring.dashboard.enabled` | `ConfigMap` labelled `grafana_dashboard: "1"` from `files/incident-responder.json`, UID `ir-<ns>`, datasource UID `monitoring.dashboard.datasourceUid` (default `prometheus`) | Grafana dashboard sidecar |
| `tracing.enabled` | `DOC_SVC_OTEL_ENABLED=true`, `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://otel-collector.monitoring.svc.cluster.local:4318`) | OTel collector |

All four default off except `monitoring.enabled`, whose ServiceMonitor still
renders only when the CRD exists, so `otterworks-main` and every other tenant
render exactly as before. The chart's `files/` copies are synced from
`observability/` by `make incident-chart-sync`; CI's `incident-chart-sync` job
fails when they drift. The NetworkPolicy admits ingress from namespaces
labelled `kubernetes.io/metadata.name: monitoring` (set by Kubernetes on every
namespace, so no extra labelling) plus `ingress-nginx`; Services stay
`ClusterIP`.

Create or redeploy through CD, falling back to the script when the runner Job
fails. The runner needs two things from the platform release
(`demo-platform/helm/demo-platform`): the `monitoring.coreos.com` rules on its
ClusterRole, and `repoHttpsUrl` + `secret.githubToken` so it can fetch the
branch (the runner image ships the tree without `.git`; the entrypoint
initializes a repository and fetches the branch shallowly). Keep the fallback on
the same host suffix as CD, otherwise external-dns drops the tenant's records:

```bash
git push origin <before-sha>:demo-incident
# fallback, from a checkout of demo-incident:
export AWS_DEFAULT_REGION=us-east-1 DB_PASSWORD='<shared RDS master password>'
export JWT_SECRET="$(openssl rand -hex 32)" SECRET_KEY_BASE="$(openssl rand -hex 64)"
scripts/deploy-tenant.sh incident --profile core --host-suffix demo.otterworks.app --ttl 72h --branch demo-incident
```

Seed and load it through a port-forward, signing with the tenant's JWT secret:

```bash
kubectl -n otterworks-incident port-forward svc/document-service 8083:8083 &
export JWT_SECRET="$(kubectl -n otterworks-incident get secret document-service-secrets -o jsonpath='{.data.JWT_SECRET}' | base64 -d)"
INCIDENT_BASE_URL=http://localhost:8083 make incident-seed
INCIDENT_BASE_URL=http://localhost:8083 make incident-load SCENARIO=n-plus-one DURATION=180
```

Shared observability (namespace `monitoring`, installed from the platform
repository): Grafana `https://grafana.otterworks.app/d/ir-otterworks-incident`,
Jaeger `https://jaeger.otterworks.app/search?service=document-service`,
Alertmanager `https://alertmanager.otterworks.app/#/alerts?filter=%7Bnamespace%3D%22otterworks-incident%22%7D`,
Prometheus `https://prometheus.otterworks.app`, or the port-forwards
`svc/prometheus-grafana 13000:80`, `svc/jaeger 16686:16686`,
`svc/prometheus-alertmanager 19093:9093`, `svc/prometheus-prometheus 19090:9090`.

A fix PR uses base `demo-incident`; merging it runs `cd-tenant.yml`, which
rebuilds document-service and redeploys the tenant. Reset to the before-state
with `git push --force origin <before-sha>:demo-incident` (rebuilds and
redeploys the before-state image) and `make incident-disarm` locally. Full
walkthrough: `.agents/skills/incident-responder/SKILL.md`, "On the shared EKS
cluster".

## Known limitations / honest gaps

- **Tier B DynamoDB** is documented but not enabled by default (IAM policy is
  ARN-pinned to the dev tables — see above). Postgres isolation via per-tenant DB
  is fully implemented.
- **Shared SNS/SQS eventing is left unwired for tenants** (`T_WIRE_EVENTING=false`)
  to avoid competing-consumer cross-talk on the shared queue. notification/search
  event pipelines are therefore inert per tenant; the request/response paths work.
- **NetworkPolicy** is applied for correctness but is only *enforced* if the
  cluster CNI has network-policy enforcement enabled.
- **`admin-service` crash-loops by design** (planted Rails logger bug on the
  golden app) — it is intentionally left broken in every tenant.
- Path-based ingress (no `--host-suffix`) serves an SPA under a sub-path with a
  rewrite; host-based routing is cleaner when wildcard DNS is available.
- **CD runner prerequisites for monitoring-enabled charts.** Once the
  `monitoring.coreos.com` CRDs exist, every chart's `ServiceMonitor` needs the
  runner service account (`otterworks-platform/demo-ops-dashboard`, ClusterRole
  `demo-platform-ops`) to manage `servicemonitors` and `prometheusrules`;
  `demo-platform/helm/demo-platform/templates/rbac.yaml` grants it, and the
  platform release must be upgraded for the grant to take effect. The runner
  also needs `GITHUB_TOKEN` + `REPO_HTTPS_URL` to check out a tenant branch;
  without them it deploys its bundled tree (no per-branch chart or overlay
  changes). Until both are in place, use the `deploy-tenant.sh` fallback above.
- **Tenant JWT secrets must be at least 32 bytes**: auth-service rejects shorter
  HS256 keys at boot (`openssl rand -hex 32`).
