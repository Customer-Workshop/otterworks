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
DB2_RELEASE="db2-archive"
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

# Same, for commands that take stdin (kubectl apply -f -). Callers pipe into it.
run_stdin() {
  if [ "${DRY_RUN}" = "1" ]; then
    printf '%b[dry-run]%b' "${YELLOW}" "${NC}"; printf ' %q' "$@"; printf ' <<stdin\n'
    sed 's/^/    | /'
    return 0
  fi
  printf '%b[run]%b' "${GREEN}" "${NC}"; printf ' %q' "$@"; printf ' <<stdin\n'
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
# overlay the state alone decides (throwaway `<x>-after` tokens have none).
token_wants_azure() {
  local token="$1"
  if [ -f "$(overlay_path "${token}")" ]; then overlay_flag "${token}" azure; return 0; fi
  [ "$(token_state "${token}")" = "after" ] && printf 'true' || printf 'false'
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

ensure_kubeconfig() {
  [ -n "${KUBERNETES_SERVICE_HOST:-}" ] && return 0
  [ "${DRY_RUN}" = "1" ] && return 0
  aws eks update-kubeconfig --name "${EKS_CLUSTER}" --region "${AWS_REGION}" --alias "${EKS_CLUSTER}" >/dev/null
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

# terraform init with a per-namespace backend. `-reconfigure` because one root
# module serves every token and the previous init may point at another state.
tf_init() {
  local dir="$1"; shift
  local args=(); mapfile -t args < <("$@")
  run terraform -chdir="${dir}" init -input=false -reconfigure "${args[@]}"
}
tf_output() { terraform -chdir="$1" output -raw "$2" 2>/dev/null || true; }

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
verify_clean() {
  local token="$1" ns rc=0 survivors
  ns="$(demo_namespace "${token}")"
  if [ "${DRY_RUN}" = "1" ]; then
    dlog "[dry-run] would verify: aws resourcegroupstaggingapi get-resources --tag-filters Key=namespace,Values=${token}"
    dlog "[dry-run] would verify: az resource list --tag namespace=${token}; az group exists -n $(azure_rg "${token}")"
    dlog "[dry-run] would verify: kubectl get ns ${ns} -> NotFound"
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
  if az_available; then
    az_login
    survivors="$(azure_resources_with_namespace "${token}")"
    if [ -n "${survivors}" ]; then derr "Azure resources still tagged namespace=${token}:"; echo "${survivors}" | sed 's/^/    /'; rc=1
    else dlog "Azure: no resources tagged namespace=${token}"; fi
    if [ "$(az group exists -n "$(azure_rg "${token}")" -o tsv 2>/dev/null)" = "true" ]; then
      derr "Azure resource group $(azure_rg "${token}") still exists"; rc=1
    else dlog "Azure: resource group $(azure_rg "${token}") absent"; fi
  else
    dwarn "Azure credentials not set; skipping the Azure survivor check"
  fi
  ensure_kubeconfig
  if kubectl get ns "${ns}" >/dev/null 2>&1; then derr "Kubernetes namespace ${ns} still exists"; rc=1
  else dlog "Kubernetes: namespace ${ns} NotFound"; fi
  return "${rc}"
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
  [ -n "${LDM_JOB_IMAGE:-}" ] && extra+=(--set "image.repository=${LDM_JOB_IMAGE%%:*}" --set "image.tag=${LDM_JOB_IMAGE##*:}")
  while IFS= read -r kv; do [ -n "${kv}" ] && extra+=(--set-string "${kv}"); done <<<"$(ldm_azure_values "${ns}")"
  # shellcheck disable=SC2086
  helm template "$(job_name "${stage}" "${run_id}")" "${JOB_CHART_DIR}" --namespace "${ns}" \
    --set "stage=${stage}" --set "namespace=${token}" --set "runId=${run_id}" \
    --set "labels.demo/namespace=${token}" "${extra[@]}" ${MIGRATION_JOB_HELM_ARGS:-}
}

# Values the chart needs that are not secrets (server, database, storage
# account, container) - read back from the archive-store Secret so migrate
# does not need Azure credentials on the operator's machine.
ldm_azure_values() {
  local ns="$1" server db acct cont
  [ "${DRY_RUN}" = "1" ] && return 0
  server="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZSQL_SERVER)"
  db="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZSQL_DATABASE)"
  acct="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STORAGE_ACCOUNT)"
  cont="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STAGING_CONTAINER)"
  [ -n "${server}" ] && printf 'azure.sqlServer=%s\n' "${server}"
  [ -n "${db}" ]     && printf 'azure.sqlDatabase=%s\n' "${db}"
  [ -n "${acct}" ]   && printf 'azure.storageAccount=%s\n' "${acct}"
  [ -n "${cont}" ]   && printf 'azure.stagingContainer=%s\n' "${cont}"
  return 0
}

# Run one stage as a Kubernetes Job, stream its log, return the container's
# exit code (§9.3). The log is appended to $3.
run_stage_job() {
  local token="$1" stage="$2" run_id="$3" logfile="$4" ns name rc
  ns="$(demo_namespace "${token}")"; name="$(job_name "${stage}" "${run_id}")"
  dlog "stage ${stage}: Job ${ns}/${name}"
  if [ "${DRY_RUN}" = "1" ]; then
    dlog "[dry-run] helm template ${name} ${JOB_CHART_DIR#"${REPO_ROOT}"/} --set stage=${stage} --set namespace=${token} --set runId=${run_id} | kubectl -n ${ns} apply -f -"
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
  local token="$1" run_id="$2" out="$3" ns acct cont
  ns="$(demo_namespace "${token}")"
  [ "${DRY_RUN}" = "1" ] && { dlog "[dry-run] would copy reconciliation.{json,csv,html} to ${out}"; return 0; }
  acct="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STORAGE_ACCOUNT)"
  cont="$(secret_value "${ns}" "${ARCHIVE_STORE_SECRET}" AZ_STAGING_CONTAINER)"
  if [ -n "${acct}" ] && az_available; then
    az_login
    local f
    for f in reconciliation.json reconciliation.csv reconciliation.html; do
      az storage blob download --auth-mode login --account-name "${acct}" -c "${cont}" \
        -n "${token}/${run_id}/${f}" -f "${out}/${f}" -o none 2>/dev/null || { dwarn "${f} not in staging"; continue; }
      dlog "copied ${f} -> ${out}/"
    done
  fi
  # Also via the app, through the shared ingress (HTML + CSV as the presenter sees them).
  local api; api="https://$(demo_api_host "${token}")/api/v1/reports/reconciliation/${run_id}"
  local ext
  for ext in html csv; do
    if curl -fsS -o "${out}/report.${ext}" "${api}.${ext}" 2>/dev/null; then dlog "copied report.${ext} from ${api}.${ext}"; fi
  done
  return 0
}
