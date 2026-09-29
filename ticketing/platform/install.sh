#!/usr/bin/env bash
# Shared, run-independent platform for the ticketing modernization demo:
# Knative Serving (Kourier, ClusterIP only), KEDA, the Strimzi operator, and a
# ServiceMonitor so Prometheus scrapes ingress-nginx latency. Idempotent.
# Nothing here creates an AWS resource: Kourier's gateway is forced to ClusterIP
# before it is applied, and traffic enters through the shared ingress-nginx.
set -euo pipefail

KNATIVE_VERSION="${KNATIVE_VERSION:-1.20.0}"
KEDA_VERSION="${KEDA_VERSION:-2.20.2}"
STRIMZI_VERSION="${STRIMZI_VERSION:-1.1.0}"
GH=https://github.com/knative

log() { printf '[platform] %s\n' "$*"; }

log "Knative Serving ${KNATIVE_VERSION}"
kubectl apply -f "${GH}/serving/releases/download/knative-v${KNATIVE_VERSION}/serving-crds.yaml"
kubectl apply -f "${GH}/serving/releases/download/knative-v${KNATIVE_VERSION}/serving-core.yaml"
kubectl -n knative-serving rollout status deploy/controller --timeout=180s

log "Kourier ${KNATIVE_VERSION} (gateway as ClusterIP)"
curl -fsSL "${GH}/net-kourier/releases/download/knative-v${KNATIVE_VERSION}/kourier.yaml" \
  | sed 's/type: LoadBalancer/type: ClusterIP/' \
  | kubectl apply -f -
if kubectl -n kourier-system get svc kourier -o jsonpath='{.spec.type}' | grep -q LoadBalancer; then
  echo "kourier Service is a LoadBalancer; refusing to continue" >&2
  exit 1
fi
kubectl patch configmap/config-network -n knative-serving --type merge \
  -p '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'
# Routes are addressed by Host header from ingress-nginx; keep the internal domain.
kubectl patch configmap/config-domain -n knative-serving --type merge \
  -p '{"data":{"svc.cluster.local":""}}'
# Scale-to-zero after 60s idle so "back to zero two minutes after the spike" holds.
kubectl patch configmap/config-autoscaler -n knative-serving --type merge \
  -p '{"data":{"enable-scale-to-zero":"true","scale-to-zero-grace-period":"30s","stable-window":"60s"}}'
kubectl patch configmap/config-features -n knative-serving --type merge \
  -p '{"data":{"kubernetes.podspec-securitycontext":"enabled"}}'

log "KEDA ${KEDA_VERSION}"
helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
helm repo add strimzi https://strimzi.io/charts/ >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install keda kedacore/keda --version "${KEDA_VERSION}" -n keda --create-namespace --wait \
  --set prometheus.operator.enabled=true --set prometheus.operator.serviceMonitor.enabled=true

log "Strimzi ${STRIMZI_VERSION} (watches all namespaces)"
helm upgrade --install strimzi strimzi/strimzi-kafka-operator --version "${STRIMZI_VERSION}" -n strimzi --create-namespace --wait \
  --set watchAnyNamespace=true --set resources.requests.cpu=100m --set resources.requests.memory=256Mi

log "ingress-nginx metrics ServiceMonitor"
kubectl apply -f - <<'YAML'
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: ingress-nginx-controller
  namespace: ingress-nginx
  labels: {app.kubernetes.io/part-of: ticketing-platform}
spec:
  selector:
    matchLabels:
      app.kubernetes.io/component: controller
      app.kubernetes.io/name: ingress-nginx
  namespaceSelector: {matchNames: [ingress-nginx]}
  endpoints:
    - port: metrics
      interval: 15s
YAML

log "done"
kubectl get pods -n knative-serving -n kourier-system 2>/dev/null || true
