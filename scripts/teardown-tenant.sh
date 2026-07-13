#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks - Per-Tenant Teardown
#
# Deletes an ephemeral tenant created by deploy-tenant.sh:
#   1. (unless --keep-db) drops the per-tenant RDS database otterworks_<ID>
#      via an in-cluster job (the Devin VM has no direct VPC access to RDS)
#   2. deletes the namespace otterworks-<ID> (all Helm releases, Redis, Meili,
#      config/secrets, ingress, quota, netpol) in one shot
#   3. removes the tenant's service-account subs from the shared IRSA role trust
#      policies (reverse of deploy-tenant's ensure_irsa_trust)
#
# Usage:
#   ./scripts/teardown-tenant.sh <ATTENDEE_ID> [--keep-db] [--keep-trust]
#
# Required env: AWS creds (exported). DB_PASSWORD needed only to drop the DB.
# ------------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/tenant-common.sh
source "${SCRIPT_DIR}/lib/tenant-common.sh"

ATTENDEE_ID=""
KEEP_DB=false
KEEP_TRUST=false
while [ $# -gt 0 ]; do
  case "$1" in
    --keep-db)    KEEP_DB=true; shift ;;
    --keep-trust) KEEP_TRUST=true; shift ;;
    -*)           err "Unknown flag: $1"; exit 1 ;;
    *)            if [ -z "${ATTENDEE_ID}" ]; then ATTENDEE_ID="$1"; else err "Unexpected arg: $1"; exit 1; fi; shift ;;
  esac
done
[ -n "${ATTENDEE_ID}" ] || { err "Usage: $0 <ATTENDEE_ID> [--keep-db] [--keep-trust]"; exit 1; }

require_bins aws kubectl jq
NS="$(tenant_namespace "${ATTENDEE_ID}")"
T_DB_NAME="$(tenant_db_name "${ATTENDEE_ID}")"

aws eks update-kubeconfig --name "${EKS_CLUSTER}" --region "${AWS_REGION}" --alias "${EKS_CLUSTER}" >/dev/null 2>&1 || true

if ! kubectl get ns "${NS}" >/dev/null 2>&1; then
  warn "Namespace ${NS} not found; nothing to delete (will still clean IRSA trust)."
else
  # --- Step 1: drop per-tenant database (best-effort, before deleting the ns) ---
  if [ "${KEEP_DB}" = false ] && [ -n "${DB_PASSWORD:-}" ]; then
    load_infra_outputs
    if [ -n "${RDS_HOST}" ]; then
      log "Dropping per-tenant database ${T_DB_NAME} (in-cluster job)..."
      kubectl -n "${NS}" delete job tenant-db-drop --ignore-not-found >/dev/null 2>&1 || true
      kubectl -n "${NS}" create secret generic tenant-db-admin \
        --from-literal=PGPASSWORD="${DB_PASSWORD}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
      kubectl apply -n "${NS}" -f - <<YAML
apiVersion: batch/v1
kind: Job
metadata:
  name: tenant-db-drop
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: psql
          image: postgres:16-alpine
          env:
            - name: PGPASSWORD
              valueFrom: { secretKeyRef: { name: tenant-db-admin, key: PGPASSWORD } }
          command: ["/bin/sh","-c"]
          args:
            - |
              CONN="host=${RDS_HOST} port=${RDS_PORT} dbname=otterworks user=${DB_USER} sslmode=prefer connect_timeout=10"
              psql "\$CONN" -c "DROP DATABASE IF EXISTS \"${T_DB_NAME}\" WITH (FORCE)" || \
                psql "\$CONN" -c "DROP DATABASE IF EXISTS \"${T_DB_NAME}\""
YAML
      kubectl -n "${NS}" wait --for=condition=complete job/tenant-db-drop --timeout=90s >/dev/null 2>&1 \
        && log "  database dropped." \
        || warn "  DB drop did not confirm; check RDS manually for ${T_DB_NAME}."
    fi
  elif [ "${KEEP_DB}" = false ]; then
    warn "DB_PASSWORD not set; skipping DB drop. Set it or drop ${T_DB_NAME} manually."
  fi

  # --- Step 2: delete the namespace (everything in it) ---
  log "Deleting namespace ${NS}..."
  kubectl delete namespace "${NS}" --wait=true --timeout=180s || \
    warn "Namespace deletion timed out; it may still be terminating."
fi

# --- Step 3: remove this tenant's subs from the shared IRSA role trust policies ---
remove_irsa_trust() {
  local d="${REPO_ROOT}/infrastructure/terraform"
  terraform -chdir="$d" init -input=false >/dev/null 2>&1 || true
  local irsa_json; irsa_json="$(terraform -chdir="$d" output -json irsa_role_arns 2>/dev/null || echo "{}")"
  local oidc_url; oidc_url="$(terraform -chdir="${REPO_ROOT}/platform/terraform" output -raw oidc_provider_url 2>/dev/null || echo "")"
  oidc_url="${oidc_url#https://}"
  [ -n "${oidc_url}" ] || { warn "OIDC URL unavailable; skipping IRSA trust cleanup."; return 0; }
  local svc role sub
  for svc in $(echo "${irsa_json}" | jq -r 'keys[]'); do
    role="otterworks-${svc}-dev"
    sub="system:serviceaccount:${NS}:${svc}"
    local doc; doc="$(aws iam get-role --role-name "${role}" --query 'Role.AssumeRolePolicyDocument' --output json 2>/dev/null || echo "")"
    [ -n "${doc}" ] || continue
    local new; new="$(echo "${doc}" | jq --arg sub "${sub}" --arg url "${oidc_url}" '
      .Statement |= map(select(
        (.Condition.StringEquals[$url+":sub"] // empty
         | (if type=="array" then . else [.] end) | index($sub)) | not))')"
    # Only update if something actually changed.
    if [ "$(echo "${doc}" | jq -cS .)" != "$(echo "${new}" | jq -cS .)" ]; then
      aws iam update-assume-role-policy --role-name "${role}" --policy-document "${new}" >/dev/null \
        && log "  IRSA trust: removed ${sub} from ${role}" \
        || warn "  failed to clean trust for ${role}"
    fi
  done
}
if [ "${KEEP_TRUST}" = false ]; then
  log "Cleaning tenant service-account subs from shared IRSA role trust policies..."
  remove_irsa_trust
fi

log "Teardown complete for tenant ${ATTENDEE_ID} (namespace ${NS})."
