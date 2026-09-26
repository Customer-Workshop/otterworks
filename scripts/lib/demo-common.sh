#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks legacy-data-migration demo — shared library (ops unit)
#
# Sourced by scripts/deploy-demo.sh, scripts/demo-destroy.sh, scripts/demo-reaper.sh
# and the Makefile demo-* targets. Layers the migration/CONTRACTS.md naming
# (§3), tagging (§3.3) and operations interface (§12) on top of the existing
# per-tenant helpers in scripts/lib/tenant-common.sh; it never re-implements
# what tenant-common.sh already provides (namespaces, DB names, infra outputs).
#
# Every mutating command goes through `run`, which prints the command and
# skips it when DRY_RUN=1 (or --dry-run on the calling script), so each script
# can be rehearsed without cloud credentials.
# ------------------------------------------------------------------------------
# shellcheck disable=SC2034  # constants are consumed by the sourcing scripts

DEMO_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${DEMO_LIB_DIR}/../.." && pwd)}"
export REPO_ROOT
# shellcheck source=tenant-common.sh
source "${DEMO_LIB_DIR}/tenant-common.sh"

# Constants (CONTRACTS.md §3.2 / §3.3) --------------------------------------
DEMO_NAME="legacy-data-migration"
DEMO_OWNER="otterworks-demo"
DEMO_HOST_SUFFIX="${HOST_SUFFIX:-otterworks.app}"
DEMO_DEFAULT_TTL="${DEMO_DEFAULT_TTL:-72h}"
DEMO_STATE_BUCKET="${DEMO_STATE_BUCKET:-otterworks-terraform-state}"
DEMO_AWS_TF_DIR="${REPO_ROOT}/infrastructure/terraform/demo-aws"
AZURE_TF_DIR="${REPO_ROOT}/infrastructure/terraform/azure"
DB2_CHART_DIR="${REPO_ROOT}/infrastructure/helm/db2-archive"
JOB_CHART_DIR="${REPO_ROOT}/infrastructure/helm/migration-job"
DB2_CREDENTIALS_SECRET="db2-archive-credentials"
ARCHIVE_STORE_SECRET="archive-store-credentials"
LDM_AZURE_SECRET="ldm-azure"
LDM_POSTGRES_SECRET="ldm-postgres"
DB2_RELEASE="db2-archive"
MIG06_FIXTURE_PATH="${MIG06_FIXTURE_PATH:-/app/migration/source/seed/fixtures/mig06_prior_run.sql}"
MANIFEST_DIR="${REPO_ROOT}/migration"
# Evidence root: per-token transcripts, tfvars, report copies (git-ignored by
# convention; copy what you want to keep into docs/demos/evidence/).
DEMO_DIR="${DEMO_DIR:-${REPO_ROOT}/.demo}"
# Services that read ARCHIVE_STORE / the archive connection (CONTRACTS §10.4).
ARCHIVE_SERVICES=(report-service audit-service admin-dashboard)

DRY_RUN="${DRY_RUN:-0}"

dlog()  { echo -e "${GREEN}[demo]${NC} $*"; }
dwarn() { echo -e "${YELLOW}[demo]${NC} $*"; }
derr()  { echo -e "${RED}[demo]${NC} $*" >&2; }
die()   { derr "$1"; exit "${2:-1}"; }

# Print a command; execute it unless dry-running. Use for anything that
# creates, changes or deletes state. Read-only lookups call tools directly.
run() {
  if [ "${DRY_RUN}" = "1" ]; then
    printf '%b[dry-run]%b' "${YELLOW}" "${NC}"; printf ' %q' "$@"; printf '\n'
    return 0
  fi
  printf '%b[run]%b' "${GREEN}" "${NC}"; printf ' %q' "$@"; printf '\n'
  "$@"
}

# Token (§3.1) ----------------------------------------------------------------
TOKEN_REGEX='^[a-z][a-z0-9]{1,11}-(before|after)$'

# Exit 2 on an invalid token (§3.1: scripts exit 2 before touching anything).
validate_token() {
  local t="$1"
  [[ "${t}" =~ ${TOKEN_REGEX} ]] || die "invalid token '${t}': must match ${TOKEN_REGEX} (e.g. d24-after)" 2
  case "${t}" in main|main-*|otterworks-main*) die "token '${t}' is reserved for the golden app" 2 ;; esac
  [ "${t%-*}" != "main" ] || die "run part 'main' is never used (§3.1)" 2
  return 0
}
token_run()   { printf '%s' "${1%-*}"; }
token_state() { printf '%s' "${1##*-}"; }
# Db2 database name: upper(RUN[0:7]) + B|A (§3.2).
db2_db_name() {
  local run; run="$(token_run "$1")"
  local suffix="A"; [ "$(token_state "$1")" = "before" ] && suffix="B"
  printf '%s%s' "$(printf '%s' "${run:0:7}" | tr '[:lower:]' '[:upper:]')" "${suffix}"
}
demo_namespace()     { tenant_namespace "$1"; }
demo_web_host()      { printf 't-%s.%s' "$1" "${DEMO_HOST_SUFFIX}"; }
demo_api_host()      { printf 'api-t-%s.%s' "$1" "${DEMO_HOST_SUFFIX}"; }
azure_rg()           { printf 'rg-otterworks-%s' "$1"; }
azure_sql_server()   { printf 'sql-otterworks-%s' "$1"; }
azure_sql_database() { printf 'sqldb-otterworks-%s' "$1"; }
azure_tfstate_key()  { printf 'otterworks/%s/terraform.tfstate' "$1"; }
aws_tfstate_key()    { printf 'otterworks/demo/%s/terraform.tfstate' "$1"; }
demo_s3_bucket()     { printf 'otterworks-ldm-%s-%s' "$1" "${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID unset}"; }
demo_ecr_repo()      { printf 'otterworks-demo/%s/ldm-job' "$1"; }
# Tag deploy-tenant resolves for an app service: the token's own build (tenant-<token>) when
# it has been pushed to ECR, otherwise the golden `main` image.
app_image_tag() {
  local token="$1" svc="$2" t; t="$(tenant_image_tag "${token}")"
  if aws ecr describe-images --repository-name "otterworks/${svc}" --image-ids "imageTag=${t}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    printf '%s' "${t}"
  else
    printf 'main'
  fi
}
# Full image reference the tenant is actually running for an app service (tag@digest as
# deploy-tenant.sh pinned it), so the Container Apps copies run the same build. Falls back
# to the ECR tag rule above when the Deployment is not there yet (dry-run, fresh namespace).
app_image_ref() {
  local token="$1" svc="$2" ns ref; ns="$(demo_namespace "${token}")"
  ref="$(kubectl -n "${ns}" get deployment "${svc}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || true)"
  if [ -n "${ref}" ]; then printf '%s' "${ref}"; return 0; fi
  aws_account_id
  printf '%s.dkr.ecr.%s.amazonaws.com/otterworks/%s:%s' "${AWS_ACCOUNT_ID}" "${AWS_REGION}" "${svc}" "${IMAGE_TAG:-$(app_image_tag "${token}" "${svc}")}"
}
# Job image tag: the migration/ tree at HEAD (`git-<sha12>`), so a rebuilt tree is a new tag.
ldm_job_tag() { printf 'git-%s' "$(git -C "${REPO_ROOT}" rev-parse --short=12 HEAD 2>/dev/null || echo dev)"; }
# Job image reference: LDM_JOB_IMAGE if set; else the token's own ECR repo at ldm_job_tag,
# falling back to the newest image pushed there (a previous deploy of the same token).
ldm_job_image() {
  local token="$1" repo tag
  [ -n "${LDM_JOB_IMAGE:-}" ] && { printf '%s' "${LDM_JOB_IMAGE}"; return 0; }
  aws_account_id
  repo="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/$(demo_ecr_repo "${token}")"
  tag="$(ldm_job_tag)"
  if [ "${DRY_RUN}" != "1" ] && ! aws ecr describe-images --repository-name "$(demo_ecr_repo "${token}")" --image-ids "imageTag=${tag}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    local newest
    newest="$(aws ecr describe-images --repository-name "$(demo_ecr_repo "${token}")" --region "${AWS_REGION}" \
      --query 'sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]' --output text 2>/dev/null || true)"
    [ -n "${newest}" ] && [ "${newest}" != "None" ] && tag="${newest}"
  fi
  printf '%s:%s' "${repo}" "${tag}"
}
# Build migration/job/Dockerfile and push it to the token's ECR repo at ldm_job_tag unless
# that tag is already there. Needs docker; the repo is created by demo-aws Terraform.
ensure_ldm_job_image() {
  local token="$1" repo tag image
  [ -n "${LDM_JOB_IMAGE:-}" ] && { dlog "LDM_JOB_IMAGE=${LDM_JOB_IMAGE} supplied; not building"; return 0; }
  aws_account_id
  repo="$(demo_ecr_repo "${token}")"; tag="$(ldm_job_tag)"
  image="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${repo}:${tag}"
  if [ "${DRY_RUN}" != "1" ] && aws ecr describe-images --repository-name "${repo}" --image-ids "imageTag=${tag}" --region "${AWS_REGION}" >/dev/null 2>&1; then
    dlog "job image ${image} already in ECR"; return 0
  fi
  require_bins docker
  if [ "${DRY_RUN}" != "1" ]; then
    aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com" >/dev/null
  fi
  run docker build --platform linux/amd64 -f "${REPO_ROOT}/migration/job/Dockerfile" -t "${image}" "${REPO_ROOT}"
  run docker push "${image}"
  dlog "job image ${image} pushed"
}
# Platform control table (demo-platform/docs/control-table-schema.md). The platform
# reaper GCs any otterworks-* namespace without a TENANT#<id>/META item as an orphan
# (grace 300s) and idle-suspends registered non-persistent tenants after an hour
# without ingress traffic - which would scale the app to zero mid-migration. A demo
# namespace is therefore registered persistent=true with its absolute expiry; the
# demo reaper (scripts/demo-reaper.sh), not the platform one, owns its lifetime.
DEMO_CONTROL_TABLE="${CONTROL_TABLE:-otterworks-demo-control}"
control_tenant_key() { jq -n --arg pk "TENANT#$1" '{PK:{S:$pk},SK:{S:"META"}}'; }
register_control_tenant() {
  local token="$1" expires="$2" now; now="$(date -u +%s)"
  local item
  item="$(jq -n --arg id "${token}" --arg ns "$(demo_namespace "${token}")" --arg db "$(tenant_db_name "${token}")" \
        --arg url "https://$(demo_web_host "${token}")" --arg api "https://$(demo_api_host "${token}")" \
        --arg branch "demo-${token}" --arg owner "${DEMO_OWNER}" --arg now "${now}" \
        --arg exp "$(iso_to_epoch "${expires}")" '{
          PK:{S:("TENANT#"+$id)}, SK:{S:"META"}, id:{S:$id}, status:{S:"active"}, tier:{S:"A"},
          namespace:{S:$ns}, db_name:{S:$db}, url:{S:$url}, api_url:{S:$api}, branch:{S:$branch},
          owner:{S:$owner}, persistent:{BOOL:true}, created_at:{N:$now}, checked_out_at:{N:$now},
          last_seen_at:{N:$now}, expires_at:{N:$exp} }')"
  aws dynamodb put-item --table-name "${DEMO_CONTROL_TABLE}" --region "${AWS_REGION}" --item "${item}" >/dev/null
}
deregister_control_tenant() {
  local token="$1"
  aws dynamodb delete-item --table-name "${DEMO_CONTROL_TABLE}" --region "${AWS_REGION}" --key "$(control_tenant_key "${token}")" >/dev/null
  aws dynamodb delete-item --table-name "${DEMO_CONTROL_TABLE}" --region "${AWS_REGION}" \
    --key "$(jq -n --arg pk "LOCK#${token}" '{PK:{S:$pk},SK:{S:"LOCK"}}')" >/dev/null 2>&1 || true
}
# The token's overlay (migration/manifests/<NS>.yaml).
overlay_path()       { printf '%s/manifests/%s.yaml' "${MANIFEST_DIR}" "$1"; }

# Read a boolean flag (azure / migrate / purge / run_job_in_azure) from the
# overlay. Overlays are small YAML files with unique keys, so a line match is
# enough; missing => "false".
overlay_flag() {
  local token="$1" key="$2" f; f="$(overlay_path "${token}")"
  [ -f "${f}" ] || { printf 'false'; return 0; }
  local v; v="$(sed -nE "s/^[[:space:]]*${key}:[[:space:]]*([a-zA-Z]+).*/\1/p" "${f}" | head -1)"
  case "${v}" in true|True|TRUE) printf 'true' ;; *) printf 'false' ;; esac
}

# Whether this token gets Azure objects: the overlay decides (§4.2); with no
# overlay nothing is Azure-backed (the default after-token is PostgreSQL + S3).
token_wants_azure() {
  local token="$1"
  if [ -f "$(overlay_path "${token}")" ]; then overlay_flag "${token}" azure; return 0; fi
  printf 'false'
}

# Whether this token is migrated at all: the overlay's migrate flag. `ldm` refuses to
# run a namespace without an overlay (CONTRACTS.md §4: purge may only be enabled there),
# so an `<x>-after` token needs migration/manifests/<x>-after.yaml before deploying.
token_wants_migrate() {
  local token="$1"
  if [ -f "$(overlay_path "${token}")" ]; then overlay_flag "${token}" migrate; return 0; fi
  printf 'false'
}

# Fail before touching anything when an after-token has no overlay: the deploy would
# otherwise get as far as the `ldm init` Job and exit 4 there.
require_overlay() {
  local token="$1"
  [ "$(token_state "${token}")" = "after" ] || return 0
  [ -f "$(overlay_path "${token}")" ] ||
    die "overlay $(overlay_path "${token}") not found; copy migration/manifests/d24-after.yaml and set namespace: ${token}" 2
}

# Expiry (§3.3) ---------------------------------------------------------------
# Compact TTL (72h, 30m, 2d) -> absolute UTC timestamp YYYY-MM-DDTHH:MM:SSZ.
ttl_to_expires() {
  local ttl="$1" num unit gnu
  num="${ttl%%[!0-9]*}"; unit="${ttl##*[0-9]}"
  [ -n "${num}" ] || die "invalid TTL '${ttl}' (use e.g. 72h, 30m, 2d)" 2
  case "${unit}" in
    h|H|"") gnu="${num} hours" ;;
    m|M)    gnu="${num} minutes" ;;
    d|D)    gnu="${num} days" ;;
    *)      die "invalid TTL unit in '${ttl}' (use h, m or d)" 2 ;;
  esac
  date -u -d "+${gnu}" +%Y-%m-%dT%H:%M:%SZ
}
now_utc()    { date -u +%Y-%m-%dT%H:%M:%SZ; }
now_stamp()  { date -u +%Y%m%dT%H%M%SZ; }
iso_to_epoch() { date -u -d "$1" +%s 2>/dev/null || echo 0; }
# Default run id per §9.1: r<UTC yyyymmddHHMMSS>.
default_run_id() { date -u +r%Y%m%d%H%M%S; }

# Kubernetes labels every demo object carries (§3.3).
demo_k8s_labels() {
  printf 'demo/namespace=%s demo/name=%s app.kubernetes.io/part-of=otterworks-ldm' "$1" "${DEMO_NAME}"
}
# Comma-separated AWS/Azure tag set.
demo_tags_kv() { printf 'namespace=%s owner=%s demo=%s expires=%s' "$1" "${DEMO_OWNER}" "${DEMO_NAME}" "$2"; }

# Transcript + timing -----------------------------------------------------------
# Tee everything from here on into .demo/<token>/<kind>-<ts>.log.
start_transcript() {
  local token="$1" kind="$2"
  TRANSCRIPT_DIR="${DEMO_DIR}/${token}"
  mkdir -p "${TRANSCRIPT_DIR}"
  TRANSCRIPT="${TRANSCRIPT_DIR}/${kind}-$(now_stamp).log"
  exec > >(tee -a "${TRANSCRIPT}") 2>&1
  dlog "transcript: ${TRANSCRIPT}"
}

STAGE_NAMES=(); STAGE_SECS=(); STAGE_RC=()
_STAGE_T0=0
stage_begin() { _STAGE_NAME="$1"; _STAGE_T0="$(date +%s)"; echo; dlog "==> ${_STAGE_NAME} ($(now_utc))"; }
stage_end() {
  local rc="${1:-0}" t1; t1="$(date +%s)"
  STAGE_NAMES+=("${_STAGE_NAME}"); STAGE_SECS+=("$((t1 - _STAGE_T0))"); STAGE_RC+=("${rc}")
  dlog "<== ${_STAGE_NAME} done in $((t1 - _STAGE_T0))s (rc=${rc})"
}
print_timing_table() {
  echo; printf '%-44s %10s %6s\n' "stage" "seconds" "rc"; printf '%-44s %10s %6s\n' "-----" "-------" "--"
  local i total=0
  for i in "${!STAGE_NAMES[@]}"; do
    printf '%-44s %10s %6s\n' "${STAGE_NAMES[$i]}" "${STAGE_SECS[$i]}" "${STAGE_RC[$i]}"
    total=$((total + STAGE_SECS[i]))
  done
  printf '%-44s %10s\n' "total" "${total}"
}

# Cloud sessions ----------------------------------------------------------------
aws_account_id() {
  AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)}"
  if [ -z "${AWS_ACCOUNT_ID}" ]; then
    [ "${DRY_RUN}" = "1" ] || die "unable to resolve the AWS account (are AWS creds exported?)"
    AWS_ACCOUNT_ID="599083837640"
  fi
  export AWS_ACCOUNT_ID
}

# Resolve the RDS master password from Secrets Manager when the operator did not export
# it; teardown-tenant.sh and the verify-clean RDS probe both refuse to certify without it.
: "${RDS_MASTER_SECRET_ID:=otterworks/dev/rds/master}"
ensure_db_password() {
  [ -n "${DB_PASSWORD:-}" ] && return 0
  [ "${DRY_RUN}" = "1" ] && return 0
  DB_PASSWORD="$(aws secretsmanager get-secret-value --secret-id "${RDS_MASTER_SECRET_ID}" \
    --region "${AWS_REGION}" --query SecretString --output text 2>/dev/null | jq -r '.password // empty' 2>/dev/null || true)"
  if [ -n "${DB_PASSWORD}" ]; then export DB_PASSWORD; dlog "DB_PASSWORD resolved from Secrets Manager ${RDS_MASTER_SECRET_ID}"
  else dwarn "DB_PASSWORD unset and ${RDS_MASTER_SECRET_ID} unreadable; RDS drop/probe will not run"; fi
}

ensure_kubeconfig() {
  [ -n "${KUBERNETES_SERVICE_HOST:-}" ] && return 0
  [ "${DRY_RUN}" = "1" ] && return 0
  aws eks update-kubeconfig --name "${EKS_CLUSTER}" --region "${AWS_REGION}" --alias "${EKS_CLUSTER}" >/dev/null
}

# Hostname of the shared ingress-nginx load balancer (the only LoadBalancer Service, AGENTS.md);
# empty when unavailable so demo-aws Terraform skips the tenant DNS records.
ingress_lb_hostname() {
  [ "${DRY_RUN}" = "1" ] && return 0
  kubectl -n ingress-nginx get svc -l app.kubernetes.io/component=controller \
    -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true
}

# demo_aws_tf_vars <token> <expires>: fills DEMO_AWS_TF_VARS (shared by apply and destroy).
demo_aws_tf_vars() {
  DEMO_AWS_TF_VARS=(-var "namespace=$1" -var "expires=$2" -var "aws_region=${AWS_REGION}" -var "eks_cluster=${EKS_CLUSTER}"
    -var "host_suffix=${DEMO_HOST_SUFFIX}" -var "ingress_hostname=$(ingress_lb_hostname)")
}

# az login with the service principal from the environment (no values printed).
# Also exports the ARM_* variables Terraform's azurerm provider expects.
az_login() {
  : "${AZURE_CLIENT_ID:?AZURE_CLIENT_ID unset}" "${AZURE_CLIENT_SECRET:?AZURE_CLIENT_SECRET unset}"
  : "${AZURE_TENANT_ID:?AZURE_TENANT_ID unset}" "${AZURE_SUBSCRIPTION_ID:?AZURE_SUBSCRIPTION_ID unset}"
  export ARM_CLIENT_ID="${AZURE_CLIENT_ID}" ARM_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
  export ARM_TENANT_ID="${AZURE_TENANT_ID}" ARM_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID}"
  [ "${DRY_RUN}" = "1" ] && { dlog "[dry-run] az login --service-principal (credentials from env)"; return 0; }
  az account show -o none 2>/dev/null && [ "$(az account show --query id -o tsv)" = "${AZURE_SUBSCRIPTION_ID}" ] && return 0
  az login --service-principal -u "${AZURE_CLIENT_ID}" -p "${AZURE_CLIENT_SECRET}" --tenant "${AZURE_TENANT_ID}" -o none
  az account set --subscription "${AZURE_SUBSCRIPTION_ID}"
}
az_available() { [ -n "${AZURE_CLIENT_ID:-}" ] && [ -n "${AZURE_CLIENT_SECRET:-}" ] && [ -n "${AZURE_TENANT_ID:-}" ] && [ -n "${AZURE_SUBSCRIPTION_ID:-}" ]; }

# Azure state backend (§3.2): shared account supplied by the environment.
azure_backend_args() {
  if [ "${DRY_RUN}" = "1" ]; then
    : "${TFSTATE_AZ_ACCOUNT:=<TFSTATE_AZ_ACCOUNT>}" "${TFSTATE_AZ_RESOURCE_GROUP:=<TFSTATE_AZ_RESOURCE_GROUP>}" "${TFSTATE_AZ_CONTAINER:=<TFSTATE_AZ_CONTAINER>}"
  fi
  : "${TFSTATE_AZ_ACCOUNT:?TFSTATE_AZ_ACCOUNT unset}" "${TFSTATE_AZ_RESOURCE_GROUP:?TFSTATE_AZ_RESOURCE_GROUP unset}"
  : "${TFSTATE_AZ_CONTAINER:?TFSTATE_AZ_CONTAINER unset}"
  printf -- '-backend-config=storage_account_name=%s\n-backend-config=resource_group_name=%s\n-backend-config=container_name=%s\n-backend-config=key=%s\n' \
    "${TFSTATE_AZ_ACCOUNT}" "${TFSTATE_AZ_RESOURCE_GROUP}" "${TFSTATE_AZ_CONTAINER}" "$(azure_tfstate_key "$1")"
}
aws_backend_args() {
  printf -- '-backend-config=bucket=%s\n-backend-config=key=%s\n-backend-config=region=%s\n' \
    "${DEMO_STATE_BUCKET}" "$(aws_tfstate_key "$1")" "${AWS_REGION}"
}

# One root module serves every token, so each token gets its own TF_DATA_DIR
# (.demo/<token>/tfdata-<root>/): backend config, provider cache and lock never
# leak between two deployments running side by side.
tf_data_dir() { printf '%s/%s/tfdata-%s' "${DEMO_DIR}" "$1" "$(basename "$2")"; }
# tf <token> <root-dir> <terraform args...>  (mutating: goes through `run`)
tf() {
  local token="$1" dir="$2"; shift 2
  mkdir -p "$(tf_data_dir "${token}" "${dir}")"
  TF_DATA_DIR="$(tf_data_dir "${token}" "${dir}")" run terraform -chdir="${dir}" "$@"
}
# terraform init with a per-namespace backend key (§3.2).
tf_init() {
  local token="$1" dir="$2"; shift 2
  local args=(); mapfile -t args < <("$@" "${token}")
  tf "${token}" "${dir}" init -input=false -reconfigure "${args[@]}"
}
tf_output() {
  TF_DATA_DIR="$(tf_data_dir "$1" "$2")" terraform -chdir="$2" output -raw "$3" 2>/dev/null || true
}

# Charts / roots written by other units may not be on the branch yet (§2).
# In dry-run the absence is reported but the rehearsal continues.
_missing() {
  if [ "${DRY_RUN}" = "1" ]; then dwarn "$1 (continuing: dry-run)"; else die "$1" 3; fi
}
require_dir() {
  local d="$1" what="$2" owner="$3"
  [ -d "${d}" ] || _missing "${what} not found at ${d#"${REPO_ROOT}"/} (owned by the ${owner} unit; merge it into demo/${DEMO_NAME} first)"
}
require_chart() {
  local d="$1" owner="$2"
  if [ ! -d "${d}" ]; then _missing "Helm chart not found at ${d#"${REPO_ROOT}"/} (owned by the ${owner} unit; merge it into demo/${DEMO_NAME} first)"
  elif [ ! -f "${d}/Chart.yaml" ]; then _missing "${d#"${REPO_ROOT}"/} has no Chart.yaml (owned by the ${owner} unit)"; fi
}

# Discovery -----------------------------------------------------------------------
# EKS egress CIDRs for the Azure SQL firewall rule (§12.4 / §14 #16): NAT
# gateway EIPs of the cluster VPC as /32; if none, the nodes' public IPs.
discover_eks_egress_cidrs() {
  local vpc ips
  vpc="$(aws eks describe-cluster --name "${EKS_CLUSTER}" --region "${AWS_REGION}" \
    --query 'cluster.resourcesVpcConfig.vpcId' --output text 2>/dev/null || true)"
  if [ -z "${vpc}" ] || [ "${vpc}" = "None" ]; then echo "[]"; return 0; fi
  ips="$(aws ec2 describe-nat-gateways --region "${AWS_REGION}" \
    --filter "Name=vpc-id,Values=${vpc}" "Name=state,Values=available" \
    --query 'NatGateways[].NatGatewayAddresses[].PublicIp' --output json 2>/dev/null || echo '[]')"
  if [ "$(jq 'length' <<<"${ips}")" -eq 0 ]; then
    ips="$(aws ec2 describe-instances --region "${AWS_REGION}" \
      --filters "Name=vpc-id,Values=${vpc}" "Name=instance-state-name,Values=running" \
      --query 'Reservations[].Instances[].PublicIpAddress' --output json 2>/dev/null | jq '[.[] | select(. != null)]')"
  fi
  jq -c '[.[] | . + "/32"] | unique' <<<"${ips}"
}

# Verification (§12.1 demo-verify-clean) ---------------------------------------------
# Lists survivors on stdout; returns 0 iff nothing tagged with the namespace remains.
aws_resources_with_namespace() {
  aws resourcegroupstaggingapi get-resources --region "${AWS_REGION}" \
    --tag-filters "Key=namespace,Values=$1" --query 'ResourceTagMappingList[].ResourceARN' --output text 2>/dev/null | tr '\t' '\n' | sed '/^$/d;/^None$/d'
}
# The Tagging API index keeps deleted EC2 resources for hours; confirm with the owning
# service before counting an ARN as a survivor. Unknown ARN types are assumed live.
aws_arn_exists() {
  local arn="$1"
  case "${arn}" in
    arn:aws:ec2:*:volume/*)
      aws ec2 describe-volumes --region "${AWS_REGION}" --volume-ids "${arn##*/}" >/dev/null 2>&1 ;;
    arn:aws:ecr:*:repository/*)
      aws ecr describe-repositories --region "${AWS_REGION}" --repository-names "${arn#*repository/}" >/dev/null 2>&1 ;;
    arn:aws:s3:::*)
      aws s3api head-bucket --bucket "${arn#arn:aws:s3:::}" >/dev/null 2>&1 ;;
    *) return 0 ;;
  esac
}
# Tagged ARNs that still exist (stale index entries are reported on stderr and dropped).
aws_live_resources_with_namespace() {
  local arn
  for arn in $(aws_resources_with_namespace "$1"); do
    if aws_arn_exists "${arn}"; then printf '%s\n' "${arn}"
    else dlog "AWS: ignoring stale tagging-index entry (resource already deleted): ${arn}" >&2; fi
  done
}
azure_resources_with_namespace() {
  az resource list --tag "namespace=$1" --query '[].id' -o tsv 2>/dev/null | sed '/^$/d'
}
# Cluster-scoped PVs of the token (the Db2 static PV outlives its namespace).
# Prints the PV names; returns non-zero when the lookup itself failed (RBAC, API
# error), which callers treat as "cannot certify", never as "none left".
demo_pvs() {
  local out
  out="$(kubectl get pv -l "demo/namespace=$1" -o name 2>&1)" || { derr "kubectl get pv failed: ${out}"; return 1; }
  printf '%s\n' "${out}" | sed '/^$/d'
}
verify_clean() {
  local token="$1" ns rc=0 survivors
  ns="$(demo_namespace "${token}")"
  if [ "${DRY_RUN}" = "1" ]; then
    dlog "[dry-run] would verify: aws resourcegroupstaggingapi get-resources --tag-filters Key=namespace,Values=${token}"
    dlog "[dry-run] would verify: az resource list --tag namespace=${token}; az group exists -n $(azure_rg "${token}")"
    dlog "[dry-run] would verify: kubectl get ns ${ns} -> NotFound; no PV labelled demo/namespace=${token}; RDS database $(tenant_db_name "${token}") absent (in-cluster psql probe)"
    return 0
  fi
  # Eventually consistent index: poll briefly before declaring a live survivor.
  local attempt=0 max_attempts="${VERIFY_RETRIES:-4}"
  survivors="$(aws_live_resources_with_namespace "${token}")"
  while [ -n "${survivors}" ] && [ "${attempt}" -lt "${max_attempts}" ]; do
    attempt=$((attempt + 1))
    dlog "AWS: $(echo "${survivors}" | wc -l) tagged resource(s) still exist; re-checking in 15s (${attempt}/${max_attempts})"
    sleep 15
    survivors="$(aws_live_resources_with_namespace "${token}")"
  done
  if [ -n "${survivors}" ]; then derr "AWS resources still tagged namespace=${token}:"; echo "${survivors}" | sed 's/^/    /'; rc=1
  else dlog "AWS: no resources tagged namespace=${token}"; fi
  # Route53 records carry no tags: check the tenant hosts by name.
  local zone_id
  zone_id="$(aws route53 list-hosted-zones-by-name --dns-name "${DEMO_HOST_SUFFIX}" --max-items 1 \
    --query "HostedZones[?Name=='${DEMO_HOST_SUFFIX}.'].Id" --output text 2>/dev/null || true)"
  if [ -n "${zone_id}" ] && [ "${zone_id}" != "None" ]; then
    survivors="$(aws route53 list-resource-record-sets --hosted-zone-id "${zone_id}" \
      --query "ResourceRecordSets[?Name=='t-${token}.${DEMO_HOST_SUFFIX}.' || Name=='api-t-${token}.${DEMO_HOST_SUFFIX}.' || Name=='admin-t-${token}.${DEMO_HOST_SUFFIX}.'].Name" --output text 2>/dev/null | tr -s '[:space:]' '\n' | sed '/^$/d')"
    if [ -n "${survivors}" ]; then derr "Route53: tenant records still exist:"; echo "${survivors}" | sed 's/^/    /'; rc=1
    else dlog "Route53: no t-${token}/api-t-${token}/admin-t-${token} records"; fi
  fi
  if az_available; then
    az_login
    survivors="$(azure_resources_with_namespace "${token}")"
    if [ -n "${survivors}" ]; then derr "Azure resources still tagged namespace=${token}:"; echo "${survivors}" | sed 's/^/    /'; rc=1
    else dlog "Azure: no resources tagged namespace=${token}"; fi
    if [ "$(az group exists -n "$(azure_rg "${token}")" -o tsv 2>/dev/null)" = "true" ]; then
      derr "Azure resource group $(azure_rg "${token}") still exists"; rc=1
    else dlog "Azure: resource group $(azure_rg "${token}") absent"; fi
  elif [ "$(token_wants_azure "${token}")" = "true" ]; then
    derr "Azure: ${token} is an Azure-backed token but AZURE_* credentials are not set; cannot certify Azure clean"; rc=1
  else
    dwarn "Azure credentials not set; skipping the Azure survivor check (before-token, no Azure objects)"
  fi
  ensure_kubeconfig
  if kubectl get ns "${ns}" >/dev/null 2>&1; then derr "Kubernetes namespace ${ns} still exists"; rc=1
  else dlog "Kubernetes: namespace ${ns} NotFound"; fi
  if ! survivors="$(demo_pvs "${token}")"; then derr "Kubernetes: could not list PVs labelled demo/namespace=${token}; not certifying clean"; rc=1
  elif [ -n "${survivors}" ]; then derr "Kubernetes: PersistentVolumes labelled demo/namespace=${token} still exist:"; echo "${survivors}" | sed 's/^/    /'; rc=1
  else dlog "Kubernetes: no PV labelled demo/namespace=${token}"; fi
  local dbname; dbname="$(tenant_db_name "${token}")"
  case "$(tenant_db_exists "${dbname}")" in
    absent)  dlog "RDS: database ${dbname} absent" ;;
    present) derr "RDS: tenant database ${dbname} still exists (teardown-tenant drop failed?)"; rc=1 ;;
    *)       derr "RDS: could not check database ${dbname} (DB_PASSWORD unset or probe failed); not certifying clean"; rc=1 ;;
  esac
  return "${rc}"
}

# Probe the shared RDS instance for a tenant database through a short in-cluster
# psql Job in ${SYSTEM_NAMESPACE} (RDS is not reachable from the operator's
# machine). Prints absent | present | unknown. Needs DB_PASSWORD, like the drop.
tenant_db_exists() {
  local db="$1" frag job secret out
  [ -n "${DB_PASSWORD:-}" ] || { printf 'unknown'; return 0; }
  load_infra_outputs >&2
  [ -n "${RDS_HOST:-}" ] || { printf 'unknown'; return 0; }
  frag="$(k8s_name_fragment "${db}")"; job="tenant-db-probe-${frag}"; secret="tenant-db-admin-probe-${frag}"
  kubectl get ns "${SYSTEM_NAMESPACE}" >/dev/null 2>&1 || kubectl create ns "${SYSTEM_NAMESPACE}" >/dev/null 2>&1 || true
  apply_db_admin_secret "${SYSTEM_NAMESPACE}" "${secret}" >&2
  kubectl -n "${SYSTEM_NAMESPACE}" delete job "${job}" --ignore-not-found >/dev/null 2>&1 || true
  kubectl apply -n "${SYSTEM_NAMESPACE}" -f - >/dev/null <<YAML
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job}
spec:
  backoffLimit: 1
  ttlSecondsAfterFinished: 120
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: psql
          image: postgres:16-alpine
          env:
            - name: PGPASSWORD
              valueFrom: { secretKeyRef: { name: ${secret}, key: PGPASSWORD } }
          command: ["/bin/sh","-c"]
          args:
            - |
              CONN="host=${RDS_HOST} port=${RDS_PORT} dbname=otterworks user=${DB_USER} sslmode=prefer connect_timeout=10"
              n=\$(psql "\$CONN" -v ON_ERROR_STOP=1 -tA -c "SELECT count(*) FROM pg_database WHERE datname='${db}'") || exit 1
              [ "\$n" = "0" ] && echo ABSENT || echo PRESENT
          resources:
            requests: { cpu: 50m, memory: 64Mi }
            limits: { cpu: 200m, memory: 128Mi }
YAML
  out="unknown"
  if kubectl -n "${SYSTEM_NAMESPACE}" wait --for=condition=complete "job/${job}" --timeout=90s >/dev/null 2>&1; then
    case "$(kubectl -n "${SYSTEM_NAMESPACE}" logs "job/${job}" 2>/dev/null | tail -1)" in
      ABSENT) out=absent ;; PRESENT) out=present ;;
    esac
  fi
  kubectl -n "${SYSTEM_NAMESPACE}" delete secret "${secret}" --ignore-not-found >/dev/null 2>&1 || true
  kubectl -n "${SYSTEM_NAMESPACE}" delete job "${job}" --ignore-not-found >/dev/null 2>&1 || true
  printf '%s' "${out}"
}

# Secrets ---------------------------------------------------------------------------
# Create/replace an Opaque Secret from KEY=VALUE pairs passed on stdin, one per
# line, so no value ever lands on an argv (mirrors apply_db_admin_secret).
apply_secret_from_stdin() {
  local ns="$1" name="$2" token="$3" line key val
  local doc="apiVersion: v1
kind: Secret
metadata:
  name: ${name}
  namespace: ${ns}
  labels:
    demo/namespace: ${token}
    demo/name: ${DEMO_NAME}
    app.kubernetes.io/part-of: otterworks-ldm
type: Opaque
data:"
  while IFS= read -r line; do
    [ -n "${line}" ] || continue
    key="${line%%=*}"; val="${line#*=}"
    doc+=$'\n'"  ${key}: $(printf '%s' "${val}" | base64 | tr -d '\n')"
  done
  if [ "${DRY_RUN}" = "1" ]; then
    dlog "[dry-run] kubectl -n ${ns} apply -f - (Secret ${name}; keys: $(printf '%s' "${doc}" | sed -n 's/^  \([A-Z_0-9a-z]*\): .*/\1/p' | tr '\n' ' '))"
    return 0
  fi
  printf '%s\n' "${doc}" | kubectl -n "${ns}" apply -f - >/dev/null
  dlog "Secret ${ns}/${name} applied"
}

# Read a Secret key (decoded) or empty.
secret_value() { kubectl -n "$1" get secret "$2" -o "jsonpath={.data.$3}" 2>/dev/null | base64 -d 2>/dev/null || true; }

# Let the BEFORE deployment's api-gateway accept the AFTER deployment's session tokens
# (JWT_PEER_SECRET), so the AFTER admin dashboard's Before/After archive panel can read
# the peer through its /peer proxy. Each tenant mints its own JWT_SECRET, so without this
# every peer read is a 401. Only the api-gateway release is upgraded; the peer's other
# services are untouched. No-op when the BEFORE namespace is not deployed yet.
trust_peer_tokens() {
  local after_token="$1" before_ns after_ns secret
  after_ns="$(demo_namespace "${after_token}")"
  before_ns="$(demo_namespace "$(token_run "${after_token}")-before")"
  [ "${DRY_RUN}" = "1" ] && { dlog "[dry-run] helm upgrade api-gateway in ${before_ns} with JWT_PEER_SECRET from ${after_ns}"; return 0; }
  if ! kubectl -n "${before_ns}" get secret api-gateway-secrets >/dev/null 2>&1; then
    dwarn "${before_ns}/api-gateway-secrets not found; peer panel on ${after_ns} will 401 until the BEFORE tenant is up"; return 0
  fi
  secret="$(kubectl -n "${after_ns}" get secret api-gateway-secrets -o jsonpath='{.data.JWT_SECRET}' | base64 -d)"
  [ -n "${secret}" ] || { dwarn "${after_ns}/api-gateway-secrets has no JWT_SECRET; not wiring peer trust"; return 0; }
  if [ "$(kubectl -n "${before_ns}" get secret api-gateway-secrets -o jsonpath='{.data.JWT_PEER_SECRET}' | base64 -d)" = "${secret}" ]; then
    dlog "${before_ns}/api-gateway already trusts ${after_ns} tokens"; return 0
  fi
  helm -n "${before_ns}" upgrade api-gateway "${REPO_ROOT}/infrastructure/helm/api-gateway" \
    --reuse-values --set-string "secrets.JWT_PEER_SECRET=${secret}" --timeout 4m >/dev/null
  kubectl -n "${before_ns}" rollout status deployment/api-gateway --timeout=240s || dwarn "api-gateway rollout in ${before_ns} not confirmed"
  dlog "${before_ns}/api-gateway now accepts ${after_ns} session tokens (JWT_PEER_SECRET)"
}

# Wire the archive-store Secret into the services that read it (§10.4). Done
# with `kubectl set env --from=secret` so the golden charts stay untouched;
# a later `helm upgrade` of those releases re-applies the chart env, so
# deploy-demo.sh runs this step last.
wire_archive_store() {
  local ns="$1" svc
  for svc in "${ARCHIVE_SERVICES[@]}"; do
    if [ "${DRY_RUN}" != "1" ] && ! kubectl -n "${ns}" get deployment "${svc}" >/dev/null 2>&1; then
      dwarn "deployment ${svc} not found in ${ns}; not wiring ${ARCHIVE_STORE_SECRET}"; continue
    fi
    # Drop env vars a previous wiring took from this Secret that the Secret no
    # longer carries (set env --from only adds/updates; stale keys would linger).
    if [ "${DRY_RUN}" != "1" ]; then
      local stale=()
      mapfile -t stale < <(comm -23 \
        <(kubectl -n "${ns}" get deployment "${svc}" -o json 2>/dev/null |
          jq -r --arg s "${ARCHIVE_STORE_SECRET}" \
            '.spec.template.spec.containers[].env[]? | select(.valueFrom.secretKeyRef.name == $s) | .name' |
          LC_ALL=C sort -u) \
        <(kubectl -n "${ns}" get secret "${ARCHIVE_STORE_SECRET}" -o json 2>/dev/null |
          jq -r '.data | keys[]' | LC_ALL=C sort -u))
      if [ "${#stale[@]}" -gt 0 ]; then
        run kubectl -n "${ns}" set env "deployment/${svc}" "${stale[@]/%/-}"
      fi
    fi
    run kubectl -n "${ns}" set env "deployment/${svc}" --from="secret/${ARCHIVE_STORE_SECRET}"
  done
  for svc in "${ARCHIVE_SERVICES[@]}"; do
    [ "${DRY_RUN}" = "1" ] && continue
    kubectl -n "${ns}" get deployment "${svc}" >/dev/null 2>&1 || continue
    kubectl -n "${ns}" rollout status "deployment/${svc}" --timeout=240s || dwarn "${svc} rollout not confirmed"
  done
}

# Migration job (§12.1 demo-migrate, §9.5) -----------------------------------------
# Render one Job from the migration-job chart for a stage and apply it. The
# chart is *templated*, never installed as a release: a Job is immutable and
# each stage/run is its own object (`ldm-<stage>-<run_id>`).
job_name() { printf 'ldm-%s-%s' "$1" "$2" | cut -c1-63; }

render_job() {
  local token="$1" stage="$2" run_id="$3" ns; ns="$(demo_namespace "${token}")"
  local -a extra=()
  # Same image deploy-demo.sh used for `ldm init` (ldm_job_image).
  local job_image="${LDM_JOB_IMAGE:-}"
  if [ -z "${job_image}" ] && [ "${DRY_RUN}" != "1" ]; then job_image="$(ldm_job_image "${token}")"; fi
  [ -n "${job_image}" ] && extra+=(--set "image.repository=${job_image%%:*}" --set "image.tag=${job_image##*:}")
  while IFS= read -r kv; do [ -n "${kv}" ] && extra+=(--set-string "${kv}"); done <<<"$(ldm_target_values "${ns}")"
  # `ldm init` also loads the MIG-06 prior-run fixture (§12.1) via --apply-sql;
  # the image ships the repo's migration/ tree at /app/migration (§13.2).
  [ "${stage}" = "init" ] && extra+=(--set-json "extraArgs=[\"--apply-sql\",\"${MIG06_FIXTURE_PATH}\"]")
  # shellcheck disable=SC2086
  helm template "$(job_name "${stage}" "${run_id}")" "${JOB_CHART_DIR}" --namespace "${ns}" \
    --set "stage=${stage}" --set "namespaceToken=${token}" --set "runId=${run_id}" \
    --set "expires=$(demo_expires "${ns}")" --set-string "env.DB2_DATABASE=$(db2_db_name "${token}")" \
    "${extra[@]}" ${MIGRATION_JOB_HELM_ARGS:-}
}

# The absolute expiry stamped on the namespace by deploy-demo.sh (demo/expires
# annotation), else EXPIRES from the environment, else now + default TTL.
demo_expires() {
  local ns="$1" v=""
  [ "${DRY_RUN}" = "1" ] || v="$(kubectl get namespace "${ns}" -o 'jsonpath={.metadata.annotations.demo/expires}' 2>/dev/null || true)"
  [ -n "${v}" ] || v="${EXPIRES:-$(ttl_to_expires "${DEMO_DEFAULT_TTL}")}"
  printf '%s' "${v}"
}

# Values the chart needs that are not secrets - read back from the archive-store
# Secret so `demo-migrate` needs neither database nor cloud credentials on the
# operator's machine. PostgreSQL + S3 (default target) and Azure (optional overlay).
ldm_target_values() {
  local ns="$1" host port db ssl bucket region role
  [ "${DRY_RUN}" = "1" ] && return 0
  host="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" PG_HOST)"
  port="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" PG_PORT)"
  db="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" PG_DATABASE)"
  ssl="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" PG_SSLMODE)"
  bucket="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" S3_STAGING_BUCKET)"
  region="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AWS_REGION)"
  role="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" LDM_JOB_ROLE_ARN)"
  [ -n "${host}" ]   && printf 'env.PG_HOST=%s\n' "${host}"
  [ -n "${port}" ]   && printf 'env.PG_PORT=%s\n' "${port}"
  [ -n "${db}" ]     && printf 'env.PG_DATABASE=%s\n' "${db}"
  [ -n "${ssl}" ]    && printf 'env.PG_SSLMODE=%s\n' "${ssl}"
  [ -n "${bucket}" ] && printf 'env.S3_STAGING_BUCKET=%s\n' "${bucket}"
  [ -n "${region}" ] && printf 'env.AWS_REGION=%s\n' "${region}"
  [ -n "${role}" ]   && printf 'serviceAccount.roleArn=%s\n' "${role}"
  ldm_azure_values "${ns}"
}

ldm_azure_values() {
  local ns="$1" server db acct cont
  [ "${DRY_RUN}" = "1" ] && return 0
  server="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZSQL_SERVER)"
  db="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZSQL_DATABASE)"
  acct="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STORAGE_ACCOUNT)"
  cont="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STAGING_CONTAINER)"
  [ -n "${server}" ] && printf 'env.AZSQL_SERVER=%s\n' "${server}"
  [ -n "${db}" ]     && printf 'env.AZSQL_DATABASE=%s\n' "${db}"
  [ -n "${acct}" ]   && printf 'env.AZ_STORAGE_ACCOUNT=%s\n' "${acct}"
  [ -n "${cont}" ]   && printf 'env.AZ_STAGING_CONTAINER=%s\n' "${cont}"
  return 0
}

# Run one stage as a Kubernetes Job, stream its log, return the container's
# exit code (§9.3). The log is appended to $3.
run_stage_job() {
  local token="$1" stage="$2" run_id="$3" logfile="$4" ns name rc
  ns="$(demo_namespace "${token}")"; name="$(job_name "${stage}" "${run_id}")"
  dlog "stage ${stage}: Job ${ns}/${name}"
  if [ "${DRY_RUN}" = "1" ]; then
    dlog "[dry-run] helm template ${name} ${JOB_CHART_DIR#"${REPO_ROOT}"/} --set stage=${stage} --set namespaceToken=${token} --set runId=${run_id} | kubectl -n ${ns} apply -f -"
    dlog "[dry-run] kubectl -n ${ns} logs -f job/${name} >> ${logfile}"
    return 0
  fi
  kubectl -n "${ns}" delete job "${name}" --ignore-not-found >/dev/null 2>&1 || true
  render_job "${token}" "${stage}" "${run_id}" | kubectl -n "${ns}" apply -f -
  # Wait for the pod to exist, then follow it. `logs -f` ends when the
  # container ends; the exit code comes from the pod status afterwards.
  local pod="" i
  for i in $(seq 1 60); do
    pod="$(kubectl -n "${ns}" get pods -l "job-name=${name}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    [ -n "${pod}" ] && break; sleep 2
  done
  [ -n "${pod}" ] || { derr "no pod appeared for job ${name}"; return 1; }
  kubectl -n "${ns}" wait --for=condition=Ready "pod/${pod}" --timeout=300s >/dev/null 2>&1 || true
  kubectl -n "${ns}" logs -f "pod/${pod}" 2>&1 | tee -a "${logfile}" || true
  kubectl -n "${ns}" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/${pod}" --timeout=10s >/dev/null 2>&1 \
    || kubectl -n "${ns}" wait --for=jsonpath='{.status.phase}'=Failed "pod/${pod}" --timeout=3600s >/dev/null 2>&1 || true
  rc="$(kubectl -n "${ns}" get "pod/${pod}" -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}' 2>/dev/null || echo 1)"
  [ -n "${rc}" ] || rc=1
  dlog "stage ${stage}: exit ${rc}"
  return "${rc}"
}

# Run the ACA job (caj-ldm-<NS>) for a stage when run_job_in_azure is set.
run_stage_aca() {
  local token="$1" stage="$2" run_id="$3" logfile="$4" rg job
  rg="$(azure_rg "${token}")"; job="caj-ldm-${token}"
  dlog "stage ${stage}: Container Apps job ${rg}/${job}"
  az_login
  if [ "${DRY_RUN}" = "1" ]; then
    dlog "[dry-run] az containerapp job start -g ${rg} -n ${job} --args ${stage} --manifest /app/migration/manifest.yaml --namespace ${token} --run-id ${run_id}"
    return 0
  fi
  local exec_name
  exec_name="$(az containerapp job start -g "${rg}" -n "${job}" \
    --args "${stage}" --manifest /app/migration/manifest.yaml --namespace "${token}" --run-id "${run_id}" \
    --query name -o tsv)"
  local status="Running"
  while [ "${status}" = "Running" ] || [ "${status}" = "Unknown" ]; do
    sleep 15
    status="$(az containerapp job execution show -g "${rg}" -n "${job}" --job-execution-name "${exec_name}" --query 'properties.status' -o tsv)"
  done
  az containerapp job logs show -g "${rg}" -n "${job}" --execution "${exec_name}" --container ldm --format text 2>/dev/null | tee -a "${logfile}" || true
  [ "${status}" = "Succeeded" ] && return 0
  derr "ACA execution ${exec_name} ended ${status}"; return 1
}

# `make demo-migrate`: EKS extract -> (EKS|ACA) load, validate -> EKS purge ->
# (EKS|ACA) reconcile (§9.5). Copies the HTML/CSV report out of the staging
# area into .demo/<token>/<run_id>/ and exits with the first non-zero code.
demo_migrate() {
  local token="$1" run_id="${2:-$(default_run_id)}" stage rc=0
  validate_token "${token}"
  [[ "${run_id}" =~ ^[a-z0-9][a-z0-9-]{2,62}$ ]] || die "invalid RUN_ID '${run_id}' (§9.1)" 2
  [ "$(overlay_flag "${token}" migrate)" = "true" ] || die "overlay $(overlay_path "${token}") has migrate: false (or is missing); ${token} is never migrated" 2
  require_chart "${JOB_CHART_DIR}" job
  aws_account_id; ensure_kubeconfig
  local out="${DEMO_DIR}/${token}/${run_id}"; mkdir -p "${out}"
  local logfile="${out}/migration.log"
  local in_azure; in_azure="$(overlay_flag "${token}" run_job_in_azure)"
  dlog "migrate ${token} run ${run_id} (run_job_in_azure=${in_azure:-false}); log ${logfile}"
  for stage in extract load validate purge reconcile; do
    stage_begin "ldm ${stage}"
    case "${stage}:${in_azure:-false}" in
      load:true|validate:true|reconcile:true) run_stage_aca "${token}" "${stage}" "${run_id}" "${logfile}" && rc=0 || rc=$? ;;
      *)                                      run_stage_job "${token}" "${stage}" "${run_id}" "${logfile}" && rc=0 || rc=$? ;;
    esac
    stage_end "${rc}"
    [ "${rc}" -eq 0 ] || break
  done
  copy_report_out "${token}" "${run_id}" "${out}" || true
  print_timing_table
  return "${rc}"
}

# RECONCILE writes reconciliation.{json,csv,html} to the staging container
# (§9.4.5); the report-service also serves them. Pull both when reachable.
copy_report_out() {
  local token="$1" run_id="$2" out="$3" ns acct cont bucket
  ns="$(demo_namespace "${token}")"
  [ "${DRY_RUN}" = "1" ] && { dlog "[dry-run] would copy reconciliation.{json,csv,html} to ${out}"; return 0; }
  # Default target: S3 staging, key <token>/<run_id>/<file> (operator AWS credentials).
  bucket="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" S3_STAGING_BUCKET)"
  if [ -n "${bucket}" ]; then
    local f
    for f in reconciliation.json reconciliation.csv reconciliation.html; do
      if aws s3 cp "s3://${bucket}/${token}/${run_id}/${f}" "${out}/${f}" --only-show-errors 2>/dev/null; then dlog "copied ${f} -> ${out}/"
      else dwarn "${f} not in s3://${bucket}/${token}/${run_id}/"; fi
    done
  fi
  acct="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STORAGE_ACCOUNT)"
  cont="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STAGING_CONTAINER)"
  if [ -n "${acct}" ] && az_available; then
    az_login
    # The operator principal holds Contributor (control plane) but no data-plane
    # blob role, so fall back to the account key when AAD auth is refused.
    local f mode
    for f in reconciliation.json reconciliation.csv reconciliation.html; do
      for mode in login key; do
        az storage blob download --auth-mode "${mode}" --account-name "${acct}" -c "${cont}" \
          -n "${token}/${run_id}/${f}" -f "${out}/${f}" -o none 2>/dev/null && break
        [ "${mode}" = key ] && { dwarn "${f} not in staging"; continue 2; }
      done
      dlog "copied ${f} -> ${out}/"
    done
  fi
  # Also via the app, through the shared ingress, as the presenter sees them
  # (§10.1: JSON at the bare run-id path, .csv and .html suffixed).
  local api; api="https://$(demo_api_host "${token}")/api/v1/reports/reconciliation/${run_id}"
  local ext url
  for ext in json html csv; do
    url="${api}"; [ "${ext}" = "json" ] || url="${api}.${ext}"
    if curl -fsS -o "${out}/report.${ext}" "${url}" 2>/dev/null; then dlog "copied report.${ext} from ${url}"; fi
  done
  return 0
}
