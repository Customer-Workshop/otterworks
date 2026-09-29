# seats — Kubernetes manifests (`<token>-after`)

Rendered with `envsubst` (only `${TOKEN}` and `${IMAGE}` are substituted):

```sh
export TOKEN=tkt01
export IMAGE=599083837640.dkr.ecr.us-east-1.amazonaws.com/otterworks-demo/ticketing/seats:tkt01-<shortsha>
for f in ticketing/services/seats/k8s/*.yaml; do envsubst '${TOKEN} ${IMAGE}' < "$f"; echo '---'; done | kubectl apply -n "${TOKEN}-after" -f -
```

| file | objects |
|------|---------|
| `00-db.yaml` | PostgreSQL 16 Deployment (`emptyDir`, ECR mirror image) + ClusterIP Service `${TOKEN}-seats-db`, credentials Secret |
| `10-seats.yaml` | Knative Service `${TOKEN}-seats` (min 0 / max 6, `rps`), ClusterIP Service `${TOKEN}-seats-metrics` for scraping |
| `20-kafka-topic.yaml` | `KafkaTopic ${TOKEN}-hold-expired` (6 partitions) on cluster `${TOKEN}-kafka` |
| `30-sweep-cronjob.yaml` | CronJob (every minute) → `POST /api/holds/sweep` |
| `40-servicemonitor.yaml` | ServiceMonitor scraping `/actuator/prometheus` |
| `50-networkpolicy.yaml` | NetworkPolicy (namespace itself, ingress-nginx, kourier-system, knative-serving, keda, monitoring) |
| `60-ingress.yaml` | ExternalName Service → `kourier-internal` + nginx Ingress for `/api/holds`, `/api/performances`, `/api/admin/expire-holds` on `${TOKEN}-after.demo.otterworks.app` |

Prerequisites owned by the integration stage: the namespace `${TOKEN}-after`, the Strimzi cluster
`${TOKEN}-kafka`, and the orders service reachable as `http://${TOKEN}-orders.${TOKEN}-after.svc.cluster.local`
(hold-expired is POSTed to its `/events/hold-expired`). No KEDA object: seats is request-driven.
