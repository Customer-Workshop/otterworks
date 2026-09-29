# Ticketing demo — platform conventions for every stage

Every stage of the modernization workflow (assess, build, integrate, verify, fix, ship)
follows these. They exist so four services built in parallel by four separate Devin
sessions deploy together without renegotiation.

## Names, tokens, labels

- A run has a **token** matching `^tkt[a-z0-9]{1,12}$` (e.g. `tkt01`). It is passed to every stage.
- Namespaces: `<token>-before` (monolith) and `<token>-after` (services + Kafka).
- Every Kubernetes object carries the label `demo.otterworks.app/run-token: <token>` and
  `demo.otterworks.app/side: before|after`, and its name starts with `<token>-` where the
  kind allows it (Knative Services and KafkaTopics included).
- Hosts: `<token>-before.demo.otterworks.app` and `<token>-after.demo.otterworks.app`
  (external-dns publishes `*.demo.otterworks.app` ingress hosts automatically; TLS via the
  `letsencrypt-prod` ClusterIssuer, DNS-01, so any host works immediately).
- Images: ECR `599083837640.dkr.ecr.us-east-1.amazonaws.com/otterworks-demo/ticketing/<svc>:<token>-<shortsha>`.
  Repositories already exist: `orders`, `seats`, `payments`, `confirmations`, `monolith`,
  `postgres` (mirror of `postgres:16-alpine`), `k6` (`k6:v1.8.1`, scratch image with the k6 binary).
  Docker Hub and public.ecr.aws are rate-limited on this network and on the nodes: pull base
  images once, and reference the ECR mirrors from manifests.
- `make demo-destroy NS=<token>` (→ `ticketing/scripts/destroy.sh`) deletes by token/label and
  fails if anything survives. Anything you create that it cannot find is a bug in your stage.

## The first extraction slice (fixed by the program)

| Service dir (`ticketing/services/<dir>`) | ECR repo | Runtime | Owns |
|---|---|---|---|
| `orders` | `orders` | Knative Service (request-driven) | order placement: orders, order items, fees, **outbox** |
| `seats` | `seats` | Knative Service (request-driven) | seat allocation: inventory, holds, hold items |
| `payments` | `payments` | Kafka consumer Deployment, **KEDA** `ScaledObject` (min 0, max 6) | payments, attempts, **idempotency key** |
| `confirmations` | `confirmations` | Knative Service (request-driven) | tickets, confirmations |

Table ownership, event names and payloads come from the assessment's decomposition note
(`ticketing/docs/decomposition.md` on the assess branch) — that note is the contract.

## Service shape

- Spring Boot 3.x, Java 21, Maven, each service builds independently (`mvn -B verify` in its dir).
- One PostgreSQL database **per service** (in-cluster `postgres:16-alpine` from the ECR mirror,
  `emptyDir` storage — the reset re-seeds; do not create PVCs or any AWS resource). Flyway `V1__…`
  migrations; H2 or Testcontainers-free tests (Docker-in-Docker is not assumed).
- Listen on 8080. `GET /actuator/health` (readiness/liveness) and `GET /actuator/prometheus`
  (Micrometer) enabled. `GET /stats` returns the service's counts for reconciliation.
- Kafka via Strimzi in `<token>-after`: cluster `<token>-kafka`, bootstrap
  `<token>-kafka-kafka-bootstrap.<token>-after.svc:9092` (plain, no auth inside the namespace).
  Topics are `KafkaTopic` resources named `<token>-<event-name>`, **6 partitions** (the KEDA cap),
  keyed by order reference so a partition replays in order.
- Knative Services: `autoscaling.knative.dev/min-scale: "0"`, `max-scale: "6"` (variable),
  `metric: rps`, target sized so the on-sale takes the service to about six pods.
- Payments consumer: manual offset commit **after** the DB transaction commits; the idempotency
  key (order reference) is a unique constraint so a replayed record is a no-op. KEDA `kafka`
  trigger, `lagThreshold` sized so the spike reaches ~6 replicas, `minReplicaCount: 0`,
  `maxReplicaCount: 6`, cooldown ≤ 60s so everything is at zero within two minutes after the spike.
- Resource requests/limits on every container, readiness/liveness probes, ClusterIP services only
  (**never** `type: LoadBalancer`; the shared ingress-nginx is the only one), NetworkPolicy allowing
  the namespace itself, `ingress-nginx`, `kourier-system`, `knative-serving`, `keda` and `monitoring`.

## Routing request-driven services through the shared ingress

Knative uses Kourier as its internal gateway (ClusterIP only). Expose a Knative Service at a path on
`<token>-after.demo.otterworks.app` with an nginx Ingress whose backend is an `ExternalName` Service
pointing at `kourier-internal.kourier-system.svc.cluster.local` (port 80), plus
`nginx.ingress.kubernetes.io/upstream-vhost: <ksvc>.<token>-after.svc.cluster.local`. This pattern was
verified on this cluster (`kourier` — not `kourier-internal` — returns 404).

## Metrics the dashboard uses

Prometheus (namespace `monitoring`) selects every `ServiceMonitor`/`PodMonitor` in the cluster.
Available: ingress-nginx request/latency histograms per ingress and namespace
(`nginx_ingress_controller_request_duration_seconds_bucket{exported_namespace=…}`), kube-state-metrics
(`kube_deployment_status_replicas`, pod counts), Knative autoscaler metrics, KEDA metrics once a
ScaledObject exists, and whatever each service exposes at `/actuator/prometheus`. Grafana
(`https://grafana.otterworks.app`, deployment `monitoring/prometheus-grafana`) loads dashboards from
ConfigMaps labelled `grafana_dashboard: "1"` in any namespace.

Load must enter through the shared ingress (k6 runs in-cluster and targets the two hosts) so both
namespaces are measured by the same histogram.

## Before state (already built)

`ticketing/monolith` (WildFly 32, Jakarta EE 10) deployed by `ticketing/scripts/deploy-before.sh <token>`
at one replica with `MONOLITH_CPU` (500m) and `PRICING_PASSES` (200). Legacy API: `POST /api/purchase`,
`GET /api/orders/{ref}`, `GET /api/performances/{id}/availability`, `GET /api/stats`, `GET /api/health`.
`ticketing/scripts/reset.sh <token>` rebuilds both namespaces; it calls
`ticketing/deploy/after/deploy.sh <token>` and `ticketing/load/seed.sh <token>` when they exist.
