#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks - Full Standalone Deploy
# 1. Provisions platform infrastructure (VPC, EKS, ECR) via Terraform
# 2. Provisions application infrastructure (RDS, DynamoDB, S3, etc.) via Terraform
# 3. Builds Docker images, pushes to ECR, and deploys via Helm
#
# Usage:
#   ./scripts/deploy-dev.sh                    # Full deploy (platform + app + helm)
#   ./scripts/deploy-dev.sh --skip-platform    # Skip platform provisioning
#   ./scripts/deploy-dev.sh --skip-terraform   # Skip all Terraform, just build+deploy
# ------------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:?ERROR: AWS_ACCOUNT_ID must be set}"
EKS_CLUSTER="${EKS_CLUSTER:-otterworks-dev}"
NAMESPACE="${NAMESPACE:-otterworks}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_PREFIX="otterworks/"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$(dirname "$0")/.." rev-parse --short HEAD)-$(date +%s)}"
DB_PASSWORD="${DB_PASSWORD:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SKIP_PLATFORM=false
SKIP_TERRAFORM=false
for arg in "$@"; do
  case "$arg" in
    --skip-platform)  SKIP_PLATFORM=true ;;
    --skip-terraform) SKIP_TERRAFORM=true ;;
  esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*" >&2; }

# Service list
BACKEND_SERVICES=(
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
)

FRONTEND_SERVICES=(
  web-app
  admin-dashboard
)

ALL_SERVICES=("${BACKEND_SERVICES[@]}" "${FRONTEND_SERVICES[@]}")

# ---------- Pre-flight checks ----------

log "Checking prerequisites..."

command -v aws >/dev/null 2>&1       || { err "aws CLI not found"; exit 1; }
command -v docker >/dev/null 2>&1    || { err "docker not found"; exit 1; }
command -v helm >/dev/null 2>&1      || { err "helm not found"; exit 1; }
command -v kubectl >/dev/null 2>&1   || { err "kubectl not found"; exit 1; }
command -v terraform >/dev/null 2>&1 || { err "terraform not found"; exit 1; }

# ---------- Step 1: Provision Platform (VPC, EKS, ECR) ----------

if [ "${SKIP_TERRAFORM}" = false ] && [ "${SKIP_PLATFORM}" = false ]; then
  log "Provisioning platform infrastructure (VPC, EKS, ECR)..."
  cd "${REPO_ROOT}/platform/terraform"
  terraform init -input=false
  terraform apply -var-file=environments/dev.tfvars -auto-approve -input=false
  cd "${REPO_ROOT}"
  log "Platform infrastructure provisioned."
else
  log "Skipping platform provisioning."
fi

# ---------- Step 2: Provision Application Infrastructure ----------

if [ "${SKIP_TERRAFORM}" = false ]; then
  DB_PASSWORD="${DB_PASSWORD:?ERROR: DB_PASSWORD must be set when running Terraform}"
  log "Provisioning application infrastructure (RDS, DynamoDB, S3, SQS, etc.)..."
  cd "${REPO_ROOT}/infrastructure/terraform"
  terraform init -input=false
  terraform apply -var="db_password=${DB_PASSWORD}" -auto-approve -input=false
  cd "${REPO_ROOT}"
  log "Application infrastructure provisioned."
else
  log "Skipping Terraform provisioning."
fi

# ---------- Capture Terraform outputs for Helm ----------

log "Reading Terraform outputs..."
TF_S3_FILE_BUCKET=$(cd "${REPO_ROOT}/infrastructure/terraform" && terraform output -raw s3_file_bucket 2>/dev/null || echo "")
TF_SNS_TOPIC_ARN=$(cd "${REPO_ROOT}/infrastructure/terraform" && terraform output -raw sns_events_topic_arn 2>/dev/null || echo "")
if [ -z "${TF_S3_FILE_BUCKET}" ]; then
  warn "Could not read s3_file_bucket from Terraform outputs; Helm will use chart defaults."
fi

# ---------- Step 3: Configure kubectl ----------

log "Configuring kubectl for EKS cluster ${EKS_CLUSTER}..."
aws eks update-kubeconfig --name "${EKS_CLUSTER}" --region "${AWS_REGION}" --alias "${EKS_CLUSTER}"

# ---------- Step 4: Create namespace ----------

log "Ensuring namespace ${NAMESPACE} exists..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# ---------- Step 5: ECR Login ----------

log "Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# ---------- Step 6: Build and push Docker images ----------

build_and_push() {
  local service=$1
  local service_dir

  if [[ " ${FRONTEND_SERVICES[*]} " == *" ${service} "* ]]; then
    service_dir="${REPO_ROOT}/frontend/${service}"
  else
    service_dir="${REPO_ROOT}/services/${service}"
  fi

  if [ ! -f "${service_dir}/Dockerfile" ]; then
    warn "No Dockerfile for ${service}, skipping..."
    return 0
  fi

  local image="${ECR_REGISTRY}/${ECR_PREFIX}${service}:${IMAGE_TAG}"
  log "Building ${service}..."
  docker build -t "${image}" "${service_dir}" --platform linux/amd64
  log "Pushing ${service}..."
  docker push "${image}"
}

log "Building and pushing Docker images..."
for service in "${ALL_SERVICES[@]}"; do
  build_and_push "${service}" || warn "Failed to build ${service}, continuing..."
done

# ---------- Step 7: Deploy via Helm ----------

deploy_service() {
  local service=$1
  local chart_dir="${REPO_ROOT}/infrastructure/helm/${service}"

  if [ ! -d "${chart_dir}" ]; then
    warn "No Helm chart for ${service}, skipping..."
    return 0
  fi

  local image="${ECR_REGISTRY}/${ECR_PREFIX}${service}"
  local extra_sets=()
  if [ "${service}" = "file-service" ] && [ -n "${TF_S3_FILE_BUCKET:-}" ]; then
    extra_sets+=(--set "config.s3Bucket=${TF_S3_FILE_BUCKET}")
  fi
  if [ "${service}" = "file-service" ] && [ -n "${TF_SNS_TOPIC_ARN:-}" ]; then
    extra_sets+=(--set "config.snsTopicArn=${TF_SNS_TOPIC_ARN}")
  fi

  log "Deploying ${service} via Helm..."
  helm upgrade --install "${service}" "${chart_dir}" \
    --namespace "${NAMESPACE}" \
    --set image.repository="${image}" \
    --set image.tag="${IMAGE_TAG}" \
    ${extra_sets[@]+"${extra_sets[@]}"} \
    --wait \
    --timeout 5m \
    || { warn "Helm deploy failed for ${service}"; return 1; }
}

log "Deploying services to EKS..."
FAILED=()
for service in "${ALL_SERVICES[@]}"; do
  deploy_service "${service}" || FAILED+=("${service}")
done

# ---------- Step 8: Verify ----------

log "Checking pod status in namespace ${NAMESPACE}..."
kubectl get pods -n "${NAMESPACE}" -o wide

if [ ${#FAILED[@]} -gt 0 ]; then
  warn "The following services failed to deploy: ${FAILED[*]}"
  exit 1
fi

log "Deployment complete! All services deployed to ${EKS_CLUSTER}/${NAMESPACE}"
echo ""
log "Useful commands:"
echo "  kubectl get pods -n ${NAMESPACE}"
echo "  kubectl get svc -n ${NAMESPACE}"
echo "  kubectl logs -n ${NAMESPACE} -l app=api-gateway"
