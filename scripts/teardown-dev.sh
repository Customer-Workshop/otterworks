#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks - Full Standalone Teardown
# Removes Helm releases, application Terraform, and platform Terraform (VPC/EKS/ECR).
#
# Usage:
#   ./scripts/teardown-dev.sh                    # Remove Helm releases + namespace only
#   ./scripts/teardown-dev.sh --destroy-infra    # Also destroy application Terraform (RDS, S3, etc.)
#   ./scripts/teardown-dev.sh --destroy-all      # Destroy everything: Helm + app Terraform + platform (EKS/VPC/ECR)
# ------------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
EKS_CLUSTER="${EKS_CLUSTER:-otterworks-dev}"
NAMESPACE="${NAMESPACE:-otterworks}"
DB_PASSWORD="${DB_PASSWORD:?ERROR: DB_PASSWORD must be set}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[teardown]${NC} $*"; }
warn() { echo -e "${YELLOW}[teardown]${NC} $*"; }
err()  { echo -e "${RED}[teardown]${NC} $*" >&2; }

DESTROY_INFRA=false
DESTROY_ALL=false
for arg in "$@"; do
  case "$arg" in
    --destroy-infra) DESTROY_INFRA=true ;;
    --destroy-all)   DESTROY_INFRA=true; DESTROY_ALL=true ;;
  esac
done

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

# ---------- Step 4: Destroy application Terraform (RDS, DynamoDB, S3, etc.) ----------

if [ "${DESTROY_INFRA}" = true ]; then
  log "Destroying application infrastructure (RDS, S3, DynamoDB, SQS, etc.)..."
  cd "${REPO_ROOT}/infrastructure/terraform"

  if [ -d ".terraform" ]; then
    terraform destroy -var="db_password=${DB_PASSWORD}" -auto-approve
  else
    terraform init -input=false
    terraform destroy -var="db_password=${DB_PASSWORD}" -auto-approve
  fi

  cd "${REPO_ROOT}"
  log "Application infrastructure destroyed."
else
  log "Skipping application Terraform destroy (pass --destroy-infra or --destroy-all)"
fi

# ---------- Step 5: Destroy platform Terraform (VPC, EKS, ECR) ----------

if [ "${DESTROY_ALL}" = true ]; then
  log "Destroying platform infrastructure (VPC, EKS, ECR)..."
  cd "${REPO_ROOT}/platform/terraform"

  if [ -d ".terraform" ]; then
    terraform destroy -var-file=environments/dev.tfvars -auto-approve
  else
    terraform init -input=false
    terraform destroy -var-file=environments/dev.tfvars -auto-approve
  fi

  cd "${REPO_ROOT}"
  log "Platform infrastructure destroyed."
else
  log "Skipping platform Terraform destroy (pass --destroy-all to also destroy VPC/EKS/ECR)"
fi

log "Teardown complete!"
echo ""
log "What was removed:"
echo "  - All Helm releases in ${NAMESPACE}"
echo "  - Kubernetes namespace ${NAMESPACE}"
if [ "${DESTROY_INFRA}" = true ]; then
  echo "  - Application Terraform resources (RDS, S3, DynamoDB, SQS, SNS, etc.)"
fi
if [ "${DESTROY_ALL}" = true ]; then
  echo "  - Platform Terraform resources (VPC, EKS cluster, ECR repositories)"
fi
echo ""
if [ "${DESTROY_ALL}" = false ]; then
  log "To fully destroy all infrastructure including VPC/EKS/ECR:"
  echo "  ./scripts/teardown-dev.sh --destroy-all"
fi
echo ""
log "To reprovision everything from scratch:"
echo "  ./scripts/deploy-dev.sh"
