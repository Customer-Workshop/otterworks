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
