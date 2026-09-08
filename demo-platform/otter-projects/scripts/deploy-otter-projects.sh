#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Build + push the Otter Projects image to ECR, apply its Terraform (DynamoDB
# table + IRSA role) and helm upgrade --install into otterworks-platform.
#
#   AWS_ACCOUNT_ID=<12 digits> ./scripts/deploy-otter-projects.sh
#
# Env:
#   AWS_ACCOUNT_ID      required — never committed; resolved from STS if unset
#   AWS_REGION          default us-east-1
#   EKS_CLUSTER         default otterworks-dev
#   NAMESPACE           default otterworks-platform
#   HOST                default projects.otterworks.app
#   IMAGE_TAG           default: current git sha
#   SECRETS_FILE        Helm values file with secret.* (generated on first run
#                       into $HOME/.otter-projects/secrets.<cluster>.yaml)
#   DEVIN_ORG_ID / DEVIN_API_KEY / DEVIN_WEBHOOK_URL / DEVIN_WEBHOOK_SECRET
#                       optional; persisted to $HOME/.otter-projects/devin.<cluster>.yaml
#                       so later deploys without them keep the wiring
#   ENVIRONMENT / TABLE_NAME / TF_STATE_KEY
#                       derived from EKS_CLUSTER (per-cluster state + names)
#   SKIP_BUILD=true     reuse an existing image tag
#   SKIP_TERRAFORM=true skip terraform apply
#   SEED=true           run the seed script inside the deployed pod afterwards
# ------------------------------------------------------------------------------
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$APP_DIR/../.." && pwd)"

AWS_REGION="${AWS_REGION:-us-east-1}"
EKS_CLUSTER="${EKS_CLUSTER:-otterworks-dev}"
NAMESPACE="${NAMESPACE:-otterworks-platform}"
HOST="${HOST:-projects.otterworks.app}"
RELEASE="${RELEASE:-otter-projects}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO="workshop/otterworks/otter-projects"
IMAGE="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"
SECRETS_FILE="${SECRETS_FILE:-$HOME/.otter-projects/secrets.${EKS_CLUSTER}.yaml}"
DEVIN_VALUES_FILE="${DEVIN_VALUES_FILE:-$HOME/.otter-projects/devin.${EKS_CLUSTER}.yaml}"
# Per-cluster isolation: the default cluster keeps its original state key and
# resource names; any other cluster gets its own state, IRSA role and table.
if [[ "$EKS_CLUSTER" == "otterworks-dev" ]]; then
  ENVIRONMENT="${ENVIRONMENT:-dev}"
  TABLE_NAME="${TABLE_NAME:-otterworks-projects}"
  TF_STATE_KEY="${TF_STATE_KEY:-demo-platform/otter-projects/terraform.tfstate}"
else
  ENVIRONMENT="${ENVIRONMENT:-${EKS_CLUSTER#otterworks-}}"
  TABLE_NAME="${TABLE_NAME:-otterworks-projects-${ENVIRONMENT}}"
  TF_STATE_KEY="${TF_STATE_KEY:-demo-platform/otter-projects/${EKS_CLUSTER}.tfstate}"
fi

log() { printf "\033[1;34m[otter-projects]\033[0m %s\n" "$*"; }

# ---- 1. image ----------------------------------------------------------------
if [[ "${SKIP_BUILD:-false}" != "true" ]]; then
  log "ensuring ECR repository ${ECR_REPO}"
  aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1 \
    || aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" \
         --image-scanning-configuration scanOnPush=true --image-tag-mutability IMMUTABLE >/dev/null
  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY" >/dev/null
  log "building ${IMAGE}"
  docker build --platform linux/amd64 -t "$IMAGE" "$APP_DIR"
  log "pushing ${IMAGE}"
  docker push "$IMAGE"
fi

# ---- 2. terraform (DynamoDB table + IRSA role) --------------------------------
if [[ "${SKIP_TERRAFORM:-false}" != "true" ]]; then
  log "terraform apply (infra/terraform)"
  terraform -chdir="$APP_DIR/infra/terraform" init -input=false -upgrade -reconfigure \
    -backend-config="key=${TF_STATE_KEY}" >/dev/null
  terraform -chdir="$APP_DIR/infra/terraform" apply -input=false -auto-approve \
    -var "aws_region=$AWS_REGION" -var "cluster_name=$EKS_CLUSTER" -var "platform_namespace=$NAMESPACE" \
    -var "environment=$ENVIRONMENT" -var "table_name=$TABLE_NAME"
fi
ROLE_NAME="$(terraform -chdir="$APP_DIR/infra/terraform" output -raw role_name 2>/dev/null || echo "otterworks-otter-projects-${ENVIRONMENT}")"

# ---- 3. secrets --------------------------------------------------------------
gen() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c "$1"; }
if [[ ! -f "$SECRETS_FILE" ]]; then
  log "generating secrets -> ${SECRETS_FILE} (kept out of git; values only live here + in the k8s Secret)"
  mkdir -p "$(dirname "$SECRETS_FILE")"
  umask 077
  cat > "$SECRETS_FILE" <<EOF
secret:
  passcode: "otter-$(gen 16)"
  sessionSecret: "$(gen 48)"
  apiKey: "op_$(gen 40)"
  webhookSecret: "$(gen 48)"
EOF
fi
# Optional Devin wiring. When any DEVIN_* env var is given the values file is
# (re)written from env so later deploys without them keep the configuration;
# values never appear on the helm command line.
if [[ -n "${DEVIN_API_KEY:-}${DEVIN_WEBHOOK_SECRET:-}${DEVIN_ORG_ID:-}${DEVIN_WEBHOOK_URL:-}" ]]; then
  log "writing Devin wiring -> ${DEVIN_VALUES_FILE}"
  mkdir -p "$(dirname "$DEVIN_VALUES_FILE")"
  umask 077
  {
    if [[ -n "${DEVIN_API_KEY:-}${DEVIN_WEBHOOK_SECRET:-}" ]]; then
      echo "secret:"
      if [[ -n "${DEVIN_API_KEY:-}" ]]; then echo "  devinApiKey: \"${DEVIN_API_KEY}\""; fi
      if [[ -n "${DEVIN_WEBHOOK_SECRET:-}" ]]; then echo "  devinWebhookSecret: \"${DEVIN_WEBHOOK_SECRET}\""; fi
    fi
    if [[ -n "${DEVIN_ORG_ID:-}${DEVIN_WEBHOOK_URL:-}" ]]; then
      echo "devin:"
      if [[ -n "${DEVIN_ORG_ID:-}" ]]; then echo "  orgId: \"${DEVIN_ORG_ID}\""; fi
      if [[ -n "${DEVIN_WEBHOOK_URL:-}" ]]; then echo "  webhookUrl: \"${DEVIN_WEBHOOK_URL}\""; fi
    fi
  } > "$DEVIN_VALUES_FILE"
fi
EXTRA_ARGS=()
[[ -f "$DEVIN_VALUES_FILE" ]] && EXTRA_ARGS+=(-f "$DEVIN_VALUES_FILE")

# ---- 4. helm -----------------------------------------------------------------
aws eks update-kubeconfig --name "$EKS_CLUSTER" --region "$AWS_REGION" >/dev/null
log "helm upgrade --install ${RELEASE} -> ${NAMESPACE} (${HOST})"
helm upgrade --install "$RELEASE" "$APP_DIR/helm/otter-projects" \
  --namespace "$NAMESPACE" \
  --set-string "awsAccountId=${AWS_ACCOUNT_ID}" \
  --set-string "image=${IMAGE}" \
  --set-string "host=${HOST}" \
  --set-string "publicUrl=https://${HOST}" \
  --set-string "table=${TABLE_NAME}" \
  --set-string "serviceAccount.roleName=${ROLE_NAME}" \
  --set-string "awsRegion=${AWS_REGION}" \
  -f "$SECRETS_FILE" \
  "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}" \
  --wait --timeout 5m

# Guardrail from AGENTS.md: nothing but ingress-nginx may be a LoadBalancer.
if kubectl -n "$NAMESPACE" get svc -l "app.kubernetes.io/name=otter-projects" -o jsonpath='{.items[*].spec.type}' | grep -q LoadBalancer; then
  echo "ERROR: otter-projects Service must be ClusterIP" >&2; exit 1
fi

# ---- 5. seed (optional) ------------------------------------------------------
if [[ "${SEED:-false}" == "true" ]]; then
  POD="$(kubectl -n "$NAMESPACE" get pod -l "app.kubernetes.io/name=otter-projects,app.kubernetes.io/component=web" -o jsonpath='{.items[0].metadata.name}')"
  log "seeding OTTER project via pod ${POD}"
  kubectl -n "$NAMESPACE" exec "$POD" -- node node_modules/tsx/dist/cli.mjs scripts/seed.ts
fi

log "deployed ${IMAGE} -> https://${HOST}"
