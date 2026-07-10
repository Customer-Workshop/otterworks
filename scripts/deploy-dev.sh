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
#   ./scripts/deploy-dev.sh --skip-build       # Reuse existing ECR images (set IMAGE_TAG)
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
# Shared JWT signing secret. MUST be identical across the gateway and every
# service that validates tokens. Generated once if not supplied; pass a stable
# value (JWT_SECRET=...) across redeploys so previously issued tokens stay valid.
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
# Rails (admin-service) session key. Stable value recommended across redeploys.
SECRET_KEY_BASE="${SECRET_KEY_BASE:-$(openssl rand -hex 64)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SKIP_PLATFORM=false
SKIP_TERRAFORM=false
SKIP_BUILD=false
for arg in "$@"; do
  case "$arg" in
    --skip-platform)  SKIP_PLATFORM=true ;;
    --skip-terraform) SKIP_TERRAFORM=true ;;
    --skip-build)     SKIP_BUILD=true ;;
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
command -v jq >/dev/null 2>&1        || { err "jq not found (required to read IRSA role ARNs from Terraform outputs)"; exit 1; }

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

if [ "${SKIP_BUILD}" = false ]; then
  log "Building and pushing Docker images..."
  for service in "${ALL_SERVICES[@]}"; do
    build_and_push "${service}" || warn "Failed to build ${service}, continuing..."
  done
else
  log "Skipping image build; reusing existing ECR images at tag ${IMAGE_TAG}."
fi

# ---------- Step 7: Deploy via Helm ----------

# The gateway proxies each route to http://<service>:<containerPort>, so every
# backend Service must be exposed on its container port (not the chart default 80).
declare -A CONTAINER_PORT=(
  [api-gateway]=8080 [auth-service]=8081 [file-service]=8082 [document-service]=8083
  [collab-service]=8084 [notification-service]=8086 [search-service]=8087
  [analytics-service]=8088 [admin-service]=8089 [audit-service]=8090 [report-service]=8091
)
# JVM services need more memory than the namespace default (256Mi) to start.
JVM_SERVICES=" auth-service report-service notification-service analytics-service "

# Populate the config/secret wiring from the application-infra Terraform outputs
# (RDS, Redis, S3, DynamoDB, SNS/SQS, IRSA roles). This closes the documented gap
# where the charts reference a ConfigMap/Secret that nothing ever creates.
load_infra_outputs() {
  local d="${REPO_ROOT}/infrastructure/terraform"
  terraform -chdir="$d" init -input=false >/dev/null 2>&1 || true
  local rds; rds="$(terraform -chdir="$d" output -raw rds_endpoint 2>/dev/null || echo "")"
  RDS_HOST="${rds%%:*}"; RDS_PORT="${rds##*:}"
  [ "$RDS_PORT" = "$rds" ] && RDS_PORT=5432 || true
  REDIS_HOST="$(terraform -chdir="$d" output -raw redis_endpoint 2>/dev/null || echo "")"
  S3_FILE_BUCKET="$(terraform -chdir="$d" output -raw s3_file_bucket 2>/dev/null || echo "")"
  S3_AUDIT_BUCKET="$(terraform -chdir="$d" output -raw s3_audit_archive_bucket 2>/dev/null || echo "")"
  DDB_FILE_META="$(terraform -chdir="$d" output -raw dynamodb_file_metadata_table 2>/dev/null || echo "")"
  DDB_AUDIT="$(terraform -chdir="$d" output -raw dynamodb_audit_events_table 2>/dev/null || echo "")"
  DDB_NOTIF="$(terraform -chdir="$d" output -raw dynamodb_notifications_table 2>/dev/null || echo "")"
  SNS_TOPIC="$(terraform -chdir="$d" output -raw sns_events_topic_arn 2>/dev/null || echo "")"
  SQS_NOTIF="$(terraform -chdir="$d" output -raw sqs_notification_queue_url 2>/dev/null || echo "")"
  IRSA_JSON="$(terraform -chdir="$d" output -json irsa_role_arns 2>/dev/null || echo "{}")"
  DB_NAME="${DB_NAME:-otterworks}"; DB_USER="${DB_USER:-otterworks_admin}"
  if [ -z "${RDS_HOST}" ]; then
    warn "Terraform outputs unavailable; services will deploy without wired config."
  fi
}

irsa_arn() { echo "${IRSA_JSON:-{}}" | jq -r --arg s "$1" '.[$s] // empty' 2>/dev/null; }

# Build the per-service Helm --set flags into the global EXTRA_ARGS array.
build_helm_args() {
  local service=$1
  EXTRA_ARGS=()
  local role; role="$(irsa_arn "$service")"
  if [ -n "$role" ]; then EXTRA_ARGS+=(--set "serviceAccount.roleArn=${role}"); fi
  if [[ " ${JVM_SERVICES} " == *" ${service} "* ]]; then
    EXTRA_ARGS+=(--set resources.requests.memory=512Mi --set resources.limits.memory=1024Mi --set resources.limits.cpu=1000m)
  fi

  case "$service" in
    web-app|admin-dashboard)
      EXTRA_ARGS+=(--set service.type=LoadBalancer --set ingress.enabled=false)
      EXTRA_ARGS+=(--set-string config.API_GATEWAY_URL=http://api-gateway:8080)
      return 0 ;;
  esac

  local port="${CONTAINER_PORT[$service]:-}"
  if [ -n "$port" ]; then EXTRA_ARGS+=(--set "service.port=${port}" --set "service.targetPort=${port}"); fi
  EXTRA_ARGS+=(--set ingress.enabled=false)

  if [ -n "${JWT_SECRET}" ]; then
    case "$service" in
      api-gateway|auth-service|document-service|collab-service|admin-service)
        EXTRA_ARGS+=(--set-string "secrets.JWT_SECRET=${JWT_SECRET}") ;;
    esac
  fi

  case "$service" in
    api-gateway) : ;; # backend service URLs default to the correct in-cluster DNS
    auth-service)
      EXTRA_ARGS+=(--set-string "config.SPRING_PROFILES_ACTIVE=prod")
      EXTRA_ARGS+=(--set-string "config.SPRING_DATASOURCE_URL=jdbc:postgresql://${RDS_HOST}:${RDS_PORT}/${DB_NAME}")
      EXTRA_ARGS+=(--set-string "config.SPRING_DATASOURCE_USERNAME=${DB_USER}")
      EXTRA_ARGS+=(--set-string "secrets.SPRING_DATASOURCE_PASSWORD=${DB_PASSWORD}") ;;
    file-service)
      EXTRA_ARGS+=(--set-string "config.AWS_REGION=${AWS_REGION}")
      EXTRA_ARGS+=(--set-string "config.S3_BUCKET=${S3_FILE_BUCKET}")
      EXTRA_ARGS+=(--set-string "config.DYNAMODB_TABLE=${DDB_FILE_META}")
      EXTRA_ARGS+=(--set-string "config.REDIS_HOST=${REDIS_HOST}" --set-string "config.REDIS_PORT=6379")
      EXTRA_ARGS+=(--set-string "config.SNS_TOPIC_ARN=${SNS_TOPIC}") ;;
    document-service)
      EXTRA_ARGS+=(--set-string "config.REDIS_HOST=${REDIS_HOST}" --set-string "config.REDIS_PORT=6379")
      EXTRA_ARGS+=(--set-string "config.DOC_SVC_AWS_REGION=${AWS_REGION}")
      EXTRA_ARGS+=(--set-string "config.DOC_SVC_SNS_TOPIC_ARN=${SNS_TOPIC}")
      EXTRA_ARGS+=(--set-string "secrets.DOC_SVC_DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${RDS_HOST}:${RDS_PORT}/${DB_NAME}") ;;
    collab-service)
      EXTRA_ARGS+=(--set-string "config.HTTP_PORT=8084" --set-string "config.NODE_ENV=production")
      EXTRA_ARGS+=(--set-string "config.REDIS_HOST=${REDIS_HOST}" --set-string "config.REDIS_PORT=6379") ;;
    notification-service)
      EXTRA_ARGS+=(--set-string "config.AWS_REGION=${AWS_REGION}")
      EXTRA_ARGS+=(--set-string "config.REDIS_HOST=${REDIS_HOST}" --set-string "config.REDIS_PORT=6379")
      EXTRA_ARGS+=(--set-string "config.DYNAMODB_TABLE_NOTIFICATIONS=${DDB_NOTIF}")
      EXTRA_ARGS+=(--set-string "config.SNS_TOPIC_ARN=${SNS_TOPIC}")
      EXTRA_ARGS+=(--set-string "config.SQS_QUEUE_URL=${SQS_NOTIF}") ;;
    search-service)
      EXTRA_ARGS+=(--set-string "config.AWS_REGION=${AWS_REGION}")
      EXTRA_ARGS+=(--set-string "config.REDIS_HOST=${REDIS_HOST}" --set-string "config.REDIS_PORT=6379")
      EXTRA_ARGS+=(--set-string "config.HOST=0.0.0.0" --set-string "config.PORT=8087")
      EXTRA_ARGS+=(--set-string "config.REQUIRE_AUTH=false" --set-string "config.SQS_ENABLED=false") ;;
    analytics-service)
      EXTRA_ARGS+=(--set-string "config.AWS_REGION=${AWS_REGION}")
      EXTRA_ARGS+=(--set-string "config.ANALYTICS_HOST=0.0.0.0" --set-string "config.PORT=8088")
      EXTRA_ARGS+=(--set-string "config.DATABASE_URL=jdbc:postgresql://${RDS_HOST}:${RDS_PORT}/${DB_NAME}")
      EXTRA_ARGS+=(--set-string "config.DATABASE_USER=${DB_USER}")
      EXTRA_ARGS+=(--set-string "secrets.DATABASE_PASSWORD=${DB_PASSWORD}") ;;
    admin-service)
      EXTRA_ARGS+=(--set-string "config.DATABASE_HOST=${RDS_HOST}" --set-string "config.DATABASE_PORT=${RDS_PORT}")
      EXTRA_ARGS+=(--set-string "config.DATABASE_USER=${DB_USER}")
      EXTRA_ARGS+=(--set-string "config.RAILS_ENV=production" --set-string "config.RAILS_LOG_TO_STDOUT=true")
      EXTRA_ARGS+=(--set-string "secrets.DATABASE_PASSWORD=${DB_PASSWORD}")
      EXTRA_ARGS+=(--set-string "secrets.SECRET_KEY_BASE=${SECRET_KEY_BASE}") ;;
    audit-service)
      EXTRA_ARGS+=(--set-string "config.Aws__Region=${AWS_REGION}")
      EXTRA_ARGS+=(--set-string "config.Aws__DynamoDbTable=${DDB_AUDIT}")
      EXTRA_ARGS+=(--set-string "config.Aws__S3ArchiveBucket=${S3_AUDIT_BUCKET}") ;;
    report-service)
      EXTRA_ARGS+=(--set-string "config.DB_HOST=${RDS_HOST}" --set-string "config.DB_PORT=${RDS_PORT}")
      EXTRA_ARGS+=(--set-string "config.DB_NAME=${DB_NAME}" --set-string "config.DB_USER=${DB_USER}")
      EXTRA_ARGS+=(--set-string "secrets.DB_PASSWORD=${DB_PASSWORD}") ;;
  esac
}

deploy_service() {
  local service=$1
  local chart_dir="${REPO_ROOT}/infrastructure/helm/${service}"

  if [ ! -d "${chart_dir}" ]; then
    warn "No Helm chart for ${service}, skipping..."
    return 0
  fi

  local image="${ECR_REGISTRY}/${ECR_PREFIX}${service}"
  build_helm_args "${service}"
  log "Deploying ${service} via Helm..."
  helm upgrade --install "${service}" "${chart_dir}" \
    --namespace "${NAMESPACE}" \
    --set image.repository="${image}" \
    --set image.tag="${IMAGE_TAG}" \
    "${EXTRA_ARGS[@]}" \
    --wait \
    --timeout 3m \
    || { warn "Helm deploy failed for ${service}"; return 1; }
}

log "Loading application-infra Terraform outputs for config wiring..."
load_infra_outputs

# Every DB-backed service (auth/document/analytics/admin/report) gets DB_PASSWORD
# injected below, so require it here too — not only inside the Terraform block,
# which is skipped on the --skip-terraform redeploy path.
DB_PASSWORD="${DB_PASSWORD:?ERROR: DB_PASSWORD must be set (exported or via Terraform run) before deploying services}"

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
