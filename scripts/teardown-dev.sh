#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks - Teardown Dev Environment
# Removes Helm releases, Kubernetes resources, and optionally Terraform infra
# ------------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
EKS_CLUSTER="${EKS_CLUSTER:-workshop-dev}"
NAMESPACE="${NAMESPACE:-decomposition-dev}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[teardown]${NC} $*"; }
warn() { echo -e "${YELLOW}[teardown]${NC} $*"; }
err()  { echo -e "${RED}[teardown]${NC} $*" >&2; }

DESTROY_INFRA="${1:-}"

# ---------- Step 1: Configure kubectl ----------

log "Configuring kubectl for EKS cluster ${EKS_CLUSTER}..."
aws eks update-kubeconfig --name "${EKS_CLUSTER}" --region "${AWS_REGION}" --alias "${EKS_CLUSTER}" 2>/dev/null || {
  warn "Could not configure kubectl — cluster may not exist"
}

# ---------- Step 2: Remove Helm releases ----------

SERVICES=(
  api-gateway
  auth-service
  file-service
  document-service
  collab-service
  notification-service
  search-service
  analytics-service
  admin-service
  audit-service
  report-service
  web-app
  admin-dashboard
)

log "Removing Helm releases from namespace ${NAMESPACE}..."
for service in "${SERVICES[@]}"; do
  helm uninstall "${service}" --namespace "${NAMESPACE}" 2>/dev/null && \
    log "  Removed ${service}" || \
    warn "  ${service} not found or already removed"
done

# ---------- Step 3: Delete namespace ----------

log "Deleting namespace ${NAMESPACE}..."
kubectl delete namespace "${NAMESPACE}" --ignore-not-found --timeout=120s || \
  warn "Namespace deletion timed out or failed"

# ---------- Step 4: Optionally destroy Terraform infra ----------

if [ "${DESTROY_INFRA}" = "--destroy-infra" ]; then
  log "Destroying Terraform infrastructure..."
  cd "${REPO_ROOT}/infrastructure/terraform"

  if [ -f ".terraform/terraform.tfstate" ] || [ -d ".terraform" ]; then
    terraform destroy -var-file=environments/dev.tfvars -auto-approve
  else
    warn "Terraform not initialized — run 'terraform init' first"
    warn "Then run: terraform destroy -var-file=environments/dev.tfvars -auto-approve"
  fi
else
  log "Skipping Terraform destroy (pass --destroy-infra to also destroy AWS resources)"
fi

log "Teardown complete!"
echo ""
log "What was removed:"
echo "  - All Helm releases in ${NAMESPACE}"
echo "  - Kubernetes namespace ${NAMESPACE}"
if [ "${DESTROY_INFRA}" = "--destroy-infra" ]; then
  echo "  - All Terraform-managed AWS resources (S3, RDS, DynamoDB, SQS, etc.)"
fi
echo ""
log "To destroy the EKS cluster itself:"
echo "  aws eks delete-nodegroup --cluster-name ${EKS_CLUSTER} --nodegroup-name default --region ${AWS_REGION}"
echo "  aws eks delete-cluster --name ${EKS_CLUSTER} --region ${AWS_REGION}"
