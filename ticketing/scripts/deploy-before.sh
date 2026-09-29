#!/usr/bin/env bash
# Deploy (or re-create) the before namespace <token>-before: shared Postgres seeded from
# ticketing/monolith/db and the monolith at one CPU-limited replica.
#   usage: deploy-before.sh <token>
source "$(dirname "$0")/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
aws_account_id; ensure_kubeconfig; check_pod_ip_capacity
NS="$(ns_before "${TOKEN}")"
MONOLITH_IMAGE="${MONOLITH_IMAGE:-${ECR_PREFIX}/monolith:$(monolith_tag)}"
aws ecr describe-images --region "${AWS_REGION}" --repository-name otterworks-demo/ticketing/monolith \
  --image-ids imageTag="${MONOLITH_IMAGE##*:}" >/dev/null 2>&1 || MONOLITH_IMAGE="$("${TKT_ROOT}/scripts/build-monolith.sh")"
export MONOLITH_IMAGE
log "before: ns=${NS} image=${MONOLITH_IMAGE##*/} cpu=${MONOLITH_CPU} pricing_passes=${PRICING_PASSES}"
render "${TOKEN}" "${TKT_ROOT}/deploy/before/10-monolith.yaml" > /tmp/"${TOKEN}"-before.yaml
kubectl apply -f <(sed -n '1,/^---$/p' /tmp/"${TOKEN}"-before.yaml | sed '$d') >/dev/null   # namespace first
kubectl -n "${NS}" create configmap "${TOKEN}-db-init" \
  --from-file=01-schema.sql="${TKT_ROOT}/monolith/db/schema.sql" \
  --from-file=02-seed.sql="${TKT_ROOT}/monolith/db/seed.sql" --dry-run=client -o yaml \
  | kubectl label --local -f - "${TOKEN_LABEL}=${TOKEN}" "${SIDE_LABEL}=before" -o yaml | kubectl apply -f - >/dev/null
kubectl apply -f /tmp/"${TOKEN}"-before.yaml
kubectl -n "${NS}" rollout status deploy/"${TOKEN}-db" --timeout=5m
kubectl -n "${NS}" rollout status deploy/"${TOKEN}-monolith" --timeout=10m
log "before ready: https://$(host_before "${TOKEN}")/app/"
