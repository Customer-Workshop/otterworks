#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks - Deploy to Dev EKS Cluster
# Builds Docker images, pushes to ECR, and deploys via Helm
# ------------------------------------------------------------------------------
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-599083837640}"
EKS_CLUSTER="${EKS_CLUSTER:-workshop-dev}"
NAMESPACE="${NAMESPACE:-decomposition-dev}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_PREFIX="workshop/otterworks-"
IMAGE_TAG="${IMAGE_TAG:-latest}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

command -v aws >/dev/null 2>&1    || { err "aws CLI not found"; exit 1; }
command -v docker >/dev/null 2>&1 || { err "docker not found"; exit 1; }
command -v helm >/dev/null 2>&1   || { err "helm not found"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { err "kubectl not found"; exit 1; }

# ---------- Step 1: Configure kubectl ----------

log "Configuring kubectl for EKS cluster ${EKS_CLUSTER}..."
aws eks update-kubeconfig --name "${EKS_CLUSTER}" --region "${AWS_REGION}" --alias "${EKS_CLUSTER}"

# ---------- Step 2: Create namespace ----------

log "Ensuring namespace ${NAMESPACE} exists..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# ---------- Step 3: ECR Login ----------

log "Logging into ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

# ---------- Step 4: Build and push Docker images ----------

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

# ---------- Step 5: Deploy via Helm ----------

deploy_service() {
  local service=$1
  local chart_dir="${REPO_ROOT}/infrastructure/helm/${service}"

  if [ ! -d "${chart_dir}" ]; then
    warn "No Helm chart for ${service}, skipping..."
    return 0
  fi

  local image="${ECR_REGISTRY}/${ECR_PREFIX}${service}"
  log "Deploying ${service} via Helm..."
  helm upgrade --install "${service}" "${chart_dir}" \
    --namespace "${NAMESPACE}" \
    --set image.repository="${image}" \
    --set image.tag="${IMAGE_TAG}" \
    --wait \
    --timeout 5m \
    || { warn "Helm deploy failed for ${service}"; return 1; }
}

log "Deploying services to EKS..."
FAILED=()
for service in "${ALL_SERVICES[@]}"; do
  deploy_service "${service}" || FAILED+=("${service}")
done

# ---------- Step 6: Verify ----------

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
