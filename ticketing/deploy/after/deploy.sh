#!/usr/bin/env bash
# Deploy (or re-create) the after namespace <token>-after: quota/limits/isolation, the Strimzi KRaft cluster
# <token>-kafka, the services' databases, the six-partition topics, the four services (Knative orders/seats/
# confirmations, KEDA-scaled payments and the orders outbox relay), the public Ingress on
# <token>-after.demo.otterworks.app and the Grafana dashboard ConfigMap; then waits for everything to be Ready.
#   usage: deploy/after/deploy.sh <token>          (called by scripts/reset.sh)
# Images come from images.sh (ORDERS_IMAGE, SEATS_IMAGE, PAYMENTS_IMAGE, CONFIRMATIONS_IMAGE override).
source "$(dirname "$0")/../../scripts/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SVC="${TKT_ROOT}/services"
aws_account_id; ensure_kubeconfig
NS="$(ns_after "${TOKEN}")"; HOST="$(host_after "${TOKEN}")"
source "${HERE}/images.sh"
export ORDERS_IMAGE SEATS_IMAGE PAYMENTS_IMAGE CONFIRMATIONS_IMAGE
WORK="$(mktemp -d "/tmp/${TOKEN}-after.XXXXXX")"; trap 'rm -rf "${WORK}"' EXIT

# Render a service manifest (envsubst '${TOKEN} ${IMAGE}' as documented by every services/*/k8s dir).
svc_render() { TOKEN="${TOKEN}" IMAGE="$2" envsubst '${TOKEN} ${IMAGE}' < "${SVC}/$1"; }
svc_apply()  { svc_render "$1" "$2" | kubectl apply -n "${NS}" -f - ; }
# Apply one service manifest file in two passes: everything except the given kind first, then that kind.
svc_apply_deferring() {
  local file="$1" image="$2" kind="$3" dir
  dir="${WORK}/$(basename "$1" .yaml)"
  mkdir -p "${dir}"; svc_render "${file}" "${image}" > "${dir}/all.yaml"
  ( cd "${dir}" && csplit -s -z -f part- all.yaml '/^---$/' '{*}' )
  for p in "${dir}"/part-*; do grep -q "^kind: ${kind}\$" "${p}" || kubectl apply -n "${NS}" -f "${p}"; done
  DEFERRED+=("${dir}")
}
apply_deferred() { local d; for d in "${DEFERRED[@]}"; do for p in "${d}"/part-*; do grep -q "^kind: $1\$" "${p}" && kubectl apply -n "${NS}" -f "${p}"; done; done; }
DEFERRED=()

log "after: ns=${NS} host=${HOST}"
# Pin every image to tag@digest (as scripts/deploy-tenant.sh does): Knative then skips its own tag-to-digest
# resolution, which cannot authenticate to ECR from the knative-serving controller on this cluster.
pin_digest() { # pin_digest <var-name>
  local img="${!1}" repo tag digest
  repo="${img#*/}"; repo="${repo%%:*}"; tag="${img##*:}"; tag="${tag%%@*}"
  digest="$(aws ecr describe-images --region "${AWS_REGION}" --repository-name "${repo}" --image-ids imageTag="${tag}" \
              --query 'imageDetails[0].imageDigest' --output text 2>/dev/null || true)"
  [ -n "${digest}" ] && [ "${digest}" != None ] || die "image not in ECR: ${img}"
  printf -v "$1" '%s' "${img%%@*}@${digest}"
  log "   image ${repo##*/}:${tag}@${digest:0:19}…"
}
pin_digest ORDERS_IMAGE; pin_digest SEATS_IMAGE; pin_digest PAYMENTS_IMAGE; pin_digest CONFIRMATIONS_IMAGE

log "1/6 namespace, quota, limits, isolation"
render "${TOKEN}" "${HERE}/00-namespace.yaml" | kubectl apply -f -

log "2/6 Kafka ${TOKEN}-kafka (KRaft, 1 ephemeral node) and the four service databases"
render "${TOKEN}" "${HERE}/10-kafka.yaml" | kubectl apply -f -
svc_apply orders/k8s/10-orders-db.yaml        "${ORDERS_IMAGE}"
svc_apply seats/k8s/00-db.yaml                "${SEATS_IMAGE}"
svc_apply payments/k8s/10-db.yaml             "${PAYMENTS_IMAGE}"
svc_apply confirmations/k8s/00-db.yaml        "${CONFIRMATIONS_IMAGE}"
for db in orders-db seats-db payments-db confirmations-db; do kubectl -n "${NS}" rollout status "deploy/${TOKEN}-${db}" --timeout=5m; done
kubectl -n "${NS}" wait "kafka/${TOKEN}-kafka" --for=condition=Ready --timeout=10m

log "3/6 topics (6 partitions each)"
svc_apply orders/k8s/20-kafka-topic.yaml        "${ORDERS_IMAGE}"
svc_apply seats/k8s/20-kafka-topic.yaml         "${SEATS_IMAGE}"
svc_apply payments/k8s/20-topics.yaml           "${PAYMENTS_IMAGE}"
svc_apply confirmations/k8s/10-kafka-topic.yaml "${CONFIRMATIONS_IMAGE}"
kubectl -n "${NS}" wait kafkatopic -l "${TOKEN_LABEL}=${TOKEN}" --for=condition=Ready --timeout=5m

log "4/6 services: Knative orders/seats/confirmations, payments + outbox relay (KEDA), monitors, policies"
svc_apply orders/k8s/30-orders-ksvc.yaml           "${ORDERS_IMAGE}"
svc_apply orders/k8s/50-monitoring.yaml            "${ORDERS_IMAGE}"
svc_apply orders/k8s/60-networkpolicy.yaml         "${ORDERS_IMAGE}"
svc_apply seats/k8s/10-seats.yaml                  "${SEATS_IMAGE}"
svc_apply seats/k8s/30-sweep-cronjob.yaml          "${SEATS_IMAGE}"
svc_apply seats/k8s/40-servicemonitor.yaml         "${SEATS_IMAGE}"
svc_apply seats/k8s/50-networkpolicy.yaml          "${SEATS_IMAGE}"
svc_apply confirmations/k8s/20-ksvc.yaml           "${CONFIRMATIONS_IMAGE}"
svc_apply confirmations/k8s/30-servicemonitor.yaml "${CONFIRMATIONS_IMAGE}"
svc_apply confirmations/k8s/40-networkpolicy.yaml  "${CONFIRMATIONS_IMAGE}"
svc_apply payments/k8s/30-payments.yaml            "${PAYMENTS_IMAGE}"
svc_apply payments/k8s/40-observability.yaml       "${PAYMENTS_IMAGE}"
# Deployment/Service first so the image is proven to boot at one replica; the ScaledObject then takes it to 0.
svc_apply_deferring orders/k8s/40-outbox-relay.yaml "${ORDERS_IMAGE}" ScaledObject
kubectl -n "${NS}" rollout status "deploy/${TOKEN}-payments" --timeout=5m
kubectl -n "${NS}" rollout status "deploy/${TOKEN}-orders-outbox-relay" --timeout=5m
svc_apply payments/k8s/50-keda.yaml "${PAYMENTS_IMAGE}"
apply_deferred ScaledObject
kubectl -n "${NS}" wait ksvc -l "${TOKEN_LABEL}=${TOKEN}" --for=condition=Ready --timeout=10m
kubectl -n "${NS}" wait scaledobject -l "${TOKEN_LABEL}=${TOKEN}" --for=condition=Ready --timeout=3m

log "5/6 public ingress https://${HOST} and Grafana dashboard"
render "${TOKEN}" "${HERE}/20-ingress.yaml" | kubectl apply -f -
svc_apply seats/k8s/60-ingress.yaml         "${SEATS_IMAGE}"
svc_apply confirmations/k8s/50-ingress.yaml "${CONFIRMATIONS_IMAGE}"
jq --arg t "${TOKEN}" '.uid = "ticketing-onsale-" + $t | .title = "Ticketing on-sale — " + $t
      | .templating.list |= map(if .name == "token" then .current = {text: $t, value: $t} else . end)' \
  "${TKT_ROOT}/dashboards/ticketing-onsale.json" > "${WORK}/ticketing-onsale-${TOKEN}.json"
kubectl -n "${NS}" create configmap "${TOKEN}-dashboard-onsale" --from-file="${WORK}/ticketing-onsale-${TOKEN}.json" --dry-run=client -o yaml \
  | kubectl label --local -f - "${TOKEN_LABEL}=${TOKEN}" "${SIDE_LABEL}=after" grafana_dashboard=1 -o yaml \
  | kubectl annotate --local -f - grafana_folder="Ticketing" -o yaml | kubectl apply -f - >/dev/null
log "   dashboard: https://grafana.otterworks.app/d/ticketing-onsale-${TOKEN}"

log "6/6 waiting for the certificate, DNS and the services to answer on https://${HOST}"
for i in $(seq 1 30); do kubectl -n "${NS}" get "certificate/${TOKEN}-after-tls" >/dev/null 2>&1 && break; sleep 2; done
kubectl -n "${NS}" wait "certificate/${TOKEN}-after-tls" --for=condition=Ready --timeout=8m
wait_http "https://${HOST}/api/stats" 200 480                        # orders (cold start through Kourier)
wait_http "https://${HOST}/api/performances/1/availability" 200 300  # seats
wait_http "https://${HOST}/api/confirmations/none" 404 300           # confirmations
log "after ready: https://${HOST}/api/stats"
