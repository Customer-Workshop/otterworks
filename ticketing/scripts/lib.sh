#!/usr/bin/env bash
# Shared helpers for the ticketing modernization demo. Every object carries the run
# token in its name and in the label demo.otterworks.app/run-token=<token>.
set -euo pipefail

TKT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${TKT_ROOT}/.." && pwd)"
AWS_REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-otterworks-dev}"
HOST_SUFFIX="${HOST_SUFFIX:-demo.otterworks.app}"
TOKEN_LABEL="demo.otterworks.app/run-token"
SIDE_LABEL="demo.otterworks.app/side"

# Monolith before-state knobs (the saturation shape the demo shows).
MONOLITH_CPU="${MONOLITH_CPU:-500m}"
MONOLITH_MEMORY="${MONOLITH_MEMORY:-1536Mi}"
PRICING_PASSES="${PRICING_PASSES:-200}"
HOLD_MINUTES="${HOLD_MINUTES:-10}"
PAYMENT_TIMEOUT_MS="${PAYMENT_TIMEOUT_MS:-4000}"

log()  { printf '[ticketing %s] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
die()  { log "ERROR: $*"; exit "${2:-1}"; }

validate_token() {
  [[ "${1:-}" =~ ^tkt[a-z0-9]{1,12}$ ]] || die "token must match ^tkt[a-z0-9]{1,12}\$ (got '${1:-}')" 2
}

ns_before() { echo "$1-before"; }
ns_after()  { echo "$1-after"; }
host_before() { echo "$1-before.${HOST_SUFFIX}"; }
host_after()  { echo "$1-after.${HOST_SUFFIX}"; }

aws_account_id() {
  AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
  ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  ECR_PREFIX="${ECR_REGISTRY}/otterworks-demo/ticketing"
  export AWS_ACCOUNT_ID ECR_REGISTRY ECR_PREFIX
}

ensure_kubeconfig() {
  kubectl version --request-timeout=5s >/dev/null 2>&1 || \
    aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${AWS_REGION}" >/dev/null
}

# Refuse to deploy into an AZ where no pod can get an IP (see scripts/pod-ip-capacity.sh).
check_pod_ip_capacity() { "${TKT_ROOT}/scripts/pod-ip-capacity.sh" --check >&2 || die "pod IP capacity check failed"; }

monolith_tag() { git -C "${REPO_ROOT}" rev-parse --short=12 "HEAD:ticketing/monolith"; }

# Render a manifest template with the token/knob variables substituted.
render() {
  TOKEN="$1" NS_BEFORE="$(ns_before "$1")" NS_AFTER="$(ns_after "$1")" \
  HOST_BEFORE="$(host_before "$1")" HOST_AFTER="$(host_after "$1")" \
  MONOLITH_CPU="${MONOLITH_CPU}" MONOLITH_MEMORY="${MONOLITH_MEMORY}" PRICING_PASSES="${PRICING_PASSES}" \
  HOLD_MINUTES="${HOLD_MINUTES}" PAYMENT_TIMEOUT_MS="${PAYMENT_TIMEOUT_MS}" \
  ECR_PREFIX="${ECR_PREFIX}" MONOLITH_IMAGE="${MONOLITH_IMAGE:-}" \
    envsubst '${TOKEN} ${NS_BEFORE} ${NS_AFTER} ${HOST_BEFORE} ${HOST_AFTER} ${MONOLITH_CPU} ${MONOLITH_MEMORY} ${PRICING_PASSES} ${HOLD_MINUTES} ${PAYMENT_TIMEOUT_MS} ${ECR_PREFIX} ${MONOLITH_IMAGE}' < "$2"
}

start_transcript() {
  local token="$1" what="$2"
  TRANSCRIPT_DIR="${TKT_ROOT}/.runs/${token}"
  mkdir -p "${TRANSCRIPT_DIR}"
  TRANSCRIPT="${TRANSCRIPT_DIR}/${what}-$(date -u +%Y%m%dT%H%M%SZ).log"
  exec > >(tee -a "${TRANSCRIPT}") 2>&1
  log "transcript: ${TRANSCRIPT#${REPO_ROOT}/}"
}

# curl against one of the token's public hosts. external-dns re-creates the A record a minute or so after
# every reset and resolvers cache the NXDOMAIN seen in between for up to 15 minutes, so pin the host to the
# shared ingress-nginx load balancer (whose own hostname always resolves) with --resolve instead of trusting
# DNS for the token host. TLS/SNI and the Host header still carry the real hostname.
#   pub_curl <url> [curl args...]
INGRESS_LB_IP=""
ingress_lb_ip() {
  local lb
  [ -n "${INGRESS_LB_IP}" ] && { echo "${INGRESS_LB_IP}"; return 0; }
  lb="$(kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  [ -n "${lb}" ] && INGRESS_LB_IP="$(dig +short +time=2 +tries=1 "${lb}" 2>/dev/null | grep -E '^[0-9]+(\.[0-9]+){3}$' | head -1 || true)"
  echo "${INGRESS_LB_IP}"
}
pub_curl() {
  local url="$1" host ip; shift
  host="${url#*://}"; host="${host%%/*}"; host="${host%%:*}"
  ip="$(ingress_lb_ip)"
  if [ -n "${ip}" ]; then curl --resolve "${host}:443:${ip}" --resolve "${host}:80:${ip}" "$@" "${url}"; else curl "$@" "${url}"; fi
}

# Poll a public URL until it answers with one of the given HTTP statuses (DNS via external-dns and the
# letsencrypt certificate both take a minute or two after a namespace is re-created).
#   wait_http <url> <statuses-regex> [timeout-seconds]
wait_http() {
  local url="$1" ok="${2:-200}" timeout="${3:-480}" started=${SECONDS} code
  while :; do
    code="$(pub_curl "${url}" -s -o /dev/null -m 30 -w '%{http_code}' 2>/dev/null || true)"
    [[ "${code}" =~ ^(${ok})$ ]] && { log "   ${url} -> ${code} after $((SECONDS - started))s"; return 0; }
    (( SECONDS - started >= timeout )) && die "${url} not answering (${ok}) after ${timeout}s (last: ${code:-none})"
    sleep 5
  done
}

# Strimzi KafkaTopics carry a topic-operator finalizer; once the entity operator is gone with the namespace the
# finalizer is never cleared and the namespace hangs in Terminating. Release the topics before deleting a namespace.
#   release_kafka_topics <namespace>
release_kafka_topics() {
  local ns="$1" t
  kubectl get crd kafkatopics.kafka.strimzi.io >/dev/null 2>&1 || return 0
  for t in $(kubectl -n "${ns}" get kafkatopic -o name 2>/dev/null); do
    kubectl -n "${ns}" patch "${t}" --type=merge -p '{"metadata":{"finalizers":null}}' >/dev/null 2>&1 || true
    kubectl -n "${ns}" delete "${t}" --wait=false --ignore-not-found >/dev/null 2>&1 || true
  done
}
