#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks legacy-data-migration demo — bring up one namespace (ops unit).
#
#   scripts/deploy-demo.sh <token> [--ttl 72h] [--image-tag TAG]
#                          [--host-suffix otterworks.app] [--dry-run]
#   scripts/deploy-demo.sh up <token> ...        (Makefile form, §12.1)
#
# <token> = <run>-<before|after>, e.g. d24-before. Always:
#   1. demo-aws Terraform      - Db2 EBS volume, S3 bucket, ECR repo (tagged)
#   2. deploy-tenant.sh        - the ordinary OtterWorks tenant (existing path)
#   3. db2-archive chart       - Db2 StatefulSet + seed hook, DB <RUN>B|<RUN>A
#   4. wiring                  - archive-store-credentials, ARCHIVE_STORE=db2
# When the token's overlay says azure: true (d24-after):
#   5. azure Terraform         - per-namespace state key, generated var file
#   6. wiring                  - Azure outputs -> Secrets, ARCHIVE_STORE=azuresql,
#                                PEER_APP_URL=<before host>, `ldm init` Job.
#                                The migration itself is NOT started here
#                                (`make demo-migrate NS=<token> RUN_ID=<id>`).
# Transcript: .demo/<token>/deploy-<ts>.log. DRY_RUN=1 / --dry-run prints
# every mutating command instead of running it.
# ------------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/demo-common.sh
source "${SCRIPT_DIR}/lib/demo-common.sh"

usage() {
  cat <<EOF
Usage: $0 [up] <token> [--ttl 72h] [--image-tag TAG] [--host-suffix ${DEMO_HOST_SUFFIX}]
          [--profile core|full] [--dry-run]
  token         <run>-<before|after>   (regex ${TOKEN_REGEX}; never main / d24-* for testing)
  --ttl         compact TTL -> absolute UTC 'expires' tag/annotation (default ${DEMO_DEFAULT_TTL})
  --image-tag   app image tag for deploy-tenant.sh (default: tag of the current branch)
  --host-suffix DNS suffix; hosts are t-<token>.<suffix> and api-t-<token>.<suffix>
  --profile     deploy-tenant.sh profile (default full)
  --dry-run     print mutating commands, touch nothing (same as DRY_RUN=1)
Env: DB_PASSWORD (RDS master, for deploy-tenant.sh), AWS creds; for after-tokens also
     AZURE_CLIENT_ID/SECRET/TENANT_ID/SUBSCRIPTION_ID and TFSTATE_AZ_ACCOUNT/RESOURCE_GROUP/CONTAINER.
EOF
}

[ "${1:-}" = "up" ] && shift
[ $# -ge 1 ] || { usage; exit 2; }
TOKEN="$1"; shift
TTL="${DEMO_DEFAULT_TTL}"; IMAGE_TAG=""; PROFILE="full"
while [ $# -gt 0 ]; do
  case "$1" in
    --ttl)         TTL="$2"; shift 2 ;;
    --image-tag)   IMAGE_TAG="$2"; shift 2 ;;
    --host-suffix) DEMO_HOST_SUFFIX="$2"; shift 2 ;;
    --profile)     PROFILE="$2"; shift 2 ;;
    --dry-run)     DRY_RUN=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) derr "unknown argument: $1"; usage; exit 2 ;;
  esac
done
export DRY_RUN

# --- validate before touching anything (§3.1) --------------------------------------
validate_token "${TOKEN}"
RUN="$(token_run "${TOKEN}")"; STATE="$(token_state "${TOKEN}")"
NS="$(demo_namespace "${TOKEN}")"
DB2_DB="$(db2_db_name "${TOKEN}")"
EXPIRES="$(ttl_to_expires "${TTL}")"
WANT_AZURE="$(token_wants_azure "${TOKEN}")"
WEB_HOST="$(demo_web_host "${TOKEN}")"; API_HOST="$(demo_api_host "${TOKEN}")"
BEFORE_HOST="$(demo_web_host "${RUN}-before")"

require_bins aws kubectl helm terraform jq
require_dir "${DEMO_AWS_TF_DIR}" "demo-aws Terraform root" ops
require_chart "${DB2_CHART_DIR}" source
if [ "${WANT_AZURE}" = "true" ]; then
  require_bins az
  require_dir "${AZURE_TF_DIR}" "Azure Terraform root" azure
  require_chart "${JOB_CHART_DIR}" job
  [ -n "$(ls "${AZURE_TF_DIR}"/*.tf 2>/dev/null)" ] || _missing "Azure Terraform root has no .tf files yet (azure unit)"
  if ! az_available; then
    [ "${DRY_RUN}" = "1" ] || die "AZURE_CLIENT_ID/AZURE_CLIENT_SECRET/AZURE_TENANT_ID/AZURE_SUBSCRIPTION_ID must be set for an azure-enabled token" 2
    dwarn "Azure credentials not set (continuing: dry-run)"
  fi
fi
if [ "${DRY_RUN}" != "1" ]; then
  : "${DB_PASSWORD:?DB_PASSWORD must be set (RDS master password; see docs/demos/${DEMO_NAME}.md)}"
fi

start_transcript "${TOKEN}" deploy
dlog "token=${TOKEN} run=${RUN} state=${STATE} namespace=${NS} db2=${DB2_DB} expires=${EXPIRES} azure=${WANT_AZURE} dry_run=${DRY_RUN}"
aws_account_id; ensure_kubeconfig
dlog "tags: $(demo_tags_kv "${TOKEN}" "${EXPIRES}")"
LABELS_KV="$(demo_k8s_labels "${TOKEN}")"

# --- 1. demo-aws Terraform ---------------------------------------------------------
stage_begin "aws terraform (demo-aws)"
tf_init "${TOKEN}" "${DEMO_AWS_TF_DIR}" aws_backend_args
tf "${TOKEN}" "${DEMO_AWS_TF_DIR}" apply -input=false -auto-approve \
  -var "namespace=${TOKEN}" -var "expires=${EXPIRES}" -var "aws_region=${AWS_REGION}" -var "eks_cluster=${EKS_CLUSTER}"
DB2_VOLUME_ID="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" db2_volume_id)"
DB2_VOLUME_AZ="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" db2_volume_az)"
DEMO_BUCKET="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" bucket_name)"
JOB_ECR_URL="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" job_repository_url)"
[ -n "${DEMO_BUCKET}" ] || DEMO_BUCKET="$(demo_s3_bucket "${TOKEN}")"
stage_end 0

# --- 2. tenant via deploy-tenant.sh --------------------------------------------------
stage_begin "deploy-tenant"
DT_ARGS=("${TOKEN}" --ttl "${TTL}" --host-suffix "${DEMO_HOST_SUFFIX}" --profile "${PROFILE}")
[ -n "${IMAGE_TAG}" ] && DT_ARGS+=(--image-tag "${IMAGE_TAG}")
run env HOST_SUFFIX="${DEMO_HOST_SUFFIX}" "${SCRIPT_DIR}/deploy-tenant.sh" "${DT_ARGS[@]}"
# Demo labels on top of the tenant labels/expiry annotation deploy-tenant sets (§3.3).
# shellcheck disable=SC2086
run kubectl label namespace "${NS}" --overwrite ${LABELS_KV}
run kubectl annotate namespace "${NS}" --overwrite "demo/expires=${EXPIRES}"
# The token's S3 prefix: an explicit prefix marker so the bucket layout is
# visible (and deletable by prefix) before the first unload lands.
run aws s3api put-object --bucket "${DEMO_BUCKET}" --key "${TOKEN}/" --content-length 0
stage_end 0

# --- 3. Db2 archive store + seed ----------------------------------------------------------
stage_begin "db2 seed"
DB2_PASSWORD="$(secret_value "${NS}" "${DB2_CREDENTIALS_SECRET}" DB2_PASSWORD)"
if [ -z "${DB2_PASSWORD}" ]; then
  DB2_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
  printf 'DB2_USER=%s\nDB2_PASSWORD=%s\nDB2INST1_PASSWORD=%s\n' db2inst1 "${DB2_PASSWORD}" "${DB2_PASSWORD}" \
    | apply_secret_from_stdin "${NS}" "${DB2_CREDENTIALS_SECRET}" "${TOKEN}"
else
  dlog "reusing existing ${DB2_CREDENTIALS_SECRET}"
fi
DB2_ARGS=(--namespace "${NS}" --create-namespace=false
  --set "dbName=${DB2_DB}" --set "credentialsSecret=${DB2_CREDENTIALS_SECRET}" --set "pv.size=20Gi"
  --set "labels.demo/namespace=${TOKEN}" --set "labels.demo/name=${DEMO_NAME}"
  --set "labels.app\.kubernetes\.io/part-of=otterworks-ldm" --set "expires=${EXPIRES}")
[ -n "${DB2_VOLUME_ID}" ] && DB2_ARGS+=(--set "pv.volumeName=${DB2_VOLUME_ID}" --set "pv.zone=${DB2_VOLUME_AZ}")
# Seed hook: enabled when the chart exposes `seed:` values (§12.1 idempotent load).
CHART_HAS_SEED=0
if grep -qE '^seed:' "${DB2_CHART_DIR}/values.yaml" 2>/dev/null; then CHART_HAS_SEED=1; DB2_ARGS+=(--set "seed.enabled=true"); fi
# shellcheck disable=SC2086
run helm upgrade --install "${DB2_RELEASE}" "${DB2_CHART_DIR}" "${DB2_ARGS[@]}" --wait --timeout 30m ${DB2_HELM_ARGS:-}
SEED_SCRIPT="${REPO_ROOT}/migration/source/seed/load.sh"
if [ "${CHART_HAS_SEED}" = "1" ]; then
  if [ "${DRY_RUN}" != "1" ]; then
    SEED_JOB="$(kubectl -n "${NS}" get jobs -l "app.kubernetes.io/instance=${DB2_RELEASE}" -o name 2>/dev/null | head -1 || true)"
    [ -n "${SEED_JOB}" ] || die "chart has seed.enabled=true but no Job labelled app.kubernetes.io/instance=${DB2_RELEASE} exists; Db2 is not seeded"
    if ! kubectl -n "${NS}" wait --for=condition=complete "${SEED_JOB}" --timeout=90m; then
      kubectl -n "${NS}" logs "${SEED_JOB}" --tail=40 2>/dev/null || true
      die "seed job ${SEED_JOB} did not complete; Db2 ${DB2_DB} is empty or partial - not continuing"
    fi
  fi
elif [ -x "${SEED_SCRIPT}" ]; then
  # Source-unit loader (migration/source/seed/load.sh); connection via env, never argv.
  if [ "${DRY_RUN}" = "1" ]; then dlog "[dry-run] ${SEED_SCRIPT#"${REPO_ROOT}"/} ${TOKEN}  (DB2_* from Secret ${DB2_CREDENTIALS_SECRET})"
  else
    DB2_HOST="${DB2_RELEASE}.${NS}.svc.cluster.local" DB2_PORT=50000 DB2_DATABASE="${DB2_DB}" DB2_USER=db2inst1 \
      DB2_PASSWORD="${DB2_PASSWORD}" KUBE_NAMESPACE="${NS}" LDM_NAMESPACE="${TOKEN}" "${SEED_SCRIPT}" "${TOKEN}"
  fi
elif [ "${DRY_RUN}" = "1" ]; then
  dwarn "neither a chart seed hook nor migration/source/seed/load.sh found (source unit); would fail"
else
  die "neither a chart seed hook nor migration/source/seed/load.sh found (source unit); Db2 ${DB2_DB} would stay empty"
fi
stage_end 0

# --- 4. wiring: archive-store-credentials (db2) --------------------------------------------
wiring_rc=0
stage_begin "wiring (db2)"
{
  printf 'ARCHIVE_STORE=db2\nLDM_NAMESPACE=%s\nLDM_RUN_TOKEN=%s\n' "${TOKEN}" "${RUN}"
  printf 'DB2_HOST=%s.%s.svc.cluster.local\nDB2_PORT=50000\nDB2_DATABASE=%s\nDB2_USER=db2inst1\nDB2_PASSWORD=%s\n' \
    "${DB2_RELEASE}" "${NS}" "${DB2_DB}" "${DB2_PASSWORD}"
  printf 'LDM_S3_BUCKET=%s\nLDM_S3_PREFIX=%s/\n' "${DEMO_BUCKET}" "${TOKEN}"
} | apply_secret_from_stdin "${NS}" "${ARCHIVE_STORE_SECRET}" "${TOKEN}"
if [ "${WANT_AZURE}" != "true" ]; then wire_archive_store "${NS}" || wiring_rc=$?; fi
stage_end "${wiring_rc}"

# --- 5/6. Azure (after) ----------------------------------------------------------------------
if [ "${WANT_AZURE}" = "true" ]; then
  stage_begin "azure terraform apply"
  az_login
  tf_init "${TOKEN}" "${AZURE_TF_DIR}" azure_backend_args
  if [ "${DRY_RUN}" = "1" ]; then EGRESS_CIDRS='["0.0.0.0/32"]'; else EGRESS_CIDRS="$(discover_eks_egress_cidrs)"; fi
  [ "$(jq 'length' <<<"${EGRESS_CIDRS}")" -gt 0 ] || die "could not discover EKS egress IPs for the Azure SQL firewall rule"
  REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  REPORT_TAG="${IMAGE_TAG:-$(tenant_image_tag "$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "demo/${DEMO_NAME}")")}"
  JOB_IMAGE="${LDM_JOB_IMAGE:-${JOB_ECR_URL:-${REGISTRY}/$(demo_ecr_repo "${TOKEN}")}:${REPORT_TAG}}"
  SESSION_LINKS="$(cat "${MANIFEST_DIR}"/sessions/*.yaml 2>/dev/null | sed -nE 's/^[[:space:]-]*url:[[:space:]]*//p' | jq -R . | jq -sc . || echo '[]')"
  TFVARS="${TRANSCRIPT_DIR}/azure.auto.tfvars.json"   # token-derived, git-ignored, no secrets
  jq -n --arg ns "${TOKEN}" --arg run "${RUN}" --arg st "${STATE}" --arg exp "${EXPIRES}" \
        --argjson cidrs "${EGRESS_CIDRS}" --arg reg "${REGISTRY}" --arg tag "${REPORT_TAG}" --arg job "${JOB_IMAGE}" \
        --arg links "${SESSION_LINKS}" --argjson inaz "$(overlay_flag "${TOKEN}" run_job_in_azure)" \
        --argjson priv "${AZURE_PRIVATE_NETWORKING:-false}" '{
          namespace:$ns, run_token:$run, state:$st, expires:$exp, owner:"otterworks-demo",
          private_networking:$priv, eks_egress_cidrs:$cidrs, run_job_in_azure:$inaz,
          registry_server:$reg, report_image:($reg+"/otterworks/report-service:"+$tag),
          audit_image:($reg+"/otterworks/audit-service:"+$tag), job_image:$job,
          session_links_json:$links }' > "${TFVARS}"
  dlog "var file ${TFVARS} (no secrets inside)"
  # ECR pull credentials for Container Apps travel via TF_VAR_*, never a file.
  if [ "${DRY_RUN}" != "1" ]; then
    TF_VAR_registry_username="AWS"; TF_VAR_registry_password="$(aws ecr get-login-password --region "${AWS_REGION}")"
    export TF_VAR_registry_username TF_VAR_registry_password
  fi
  # No saved plan file: a plan embeds TF_VAR_registry_password in clear text.
  # The plan output itself is in the transcript.
  tf "${TOKEN}" "${AZURE_TF_DIR}" apply -input=false -auto-approve -var-file="${TFVARS}"
  unset TF_VAR_registry_password
  stage_end 0

  stage_begin "wiring (azuresql)"
  AZSQL_SERVER="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" sql_server_fqdn)"
  AZSQL_DATABASE="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" sql_database_name)"
  AZ_STORAGE_ACCOUNT="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" storage_account_name)"
  AZ_STAGING_CONTAINER="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" staging_container)"
  KEY_VAULT="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" key_vault_name)"
  MI_CLIENT_ID="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" managed_identity_client_id)"
  ACA_REPORT_URL="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" report_fqdn)"
  ACA_AUDIT_URL="$(tf_output "${TOKEN}" "${AZURE_TF_DIR}" audit_fqdn)"
  if [ "${DRY_RUN}" = "1" ]; then
    AZSQL_SERVER="${AZSQL_SERVER:-$(azure_sql_server "${TOKEN}").database.windows.net}"
    AZSQL_DATABASE="${AZSQL_DATABASE:-$(azure_sql_database "${TOKEN}")}"
    AZ_STAGING_CONTAINER="${AZ_STAGING_CONTAINER:-staging-${TOKEN}}"
    AZSQL_USER="ldm_admin"; AZSQL_PASSWORD="<from key vault>"
  else
    { [ -n "${AZSQL_SERVER}" ] && [ -n "${KEY_VAULT}" ]; } || die "Azure Terraform did not expose sql_server_fqdn / key_vault_name outputs (§11.2)"
    # The SQL credential lives only in Key Vault (§11.3); read it into the
    # Secret without echoing it.
    AZSQL_USER="$(az keyvault secret show --vault-name "${KEY_VAULT}" -n azsql-admin-user --query value -o tsv)"
    AZSQL_PASSWORD="$(az keyvault secret show --vault-name "${KEY_VAULT}" -n azsql-admin-password --query value -o tsv)"
    AZSQL_READER_USER="$(az keyvault secret show --vault-name "${KEY_VAULT}" -n azsql-reader-user --query value -o tsv 2>/dev/null || true)"
    AZSQL_READER_PASSWORD="$(az keyvault secret show --vault-name "${KEY_VAULT}" -n azsql-reader-password --query value -o tsv 2>/dev/null || true)"
    AZ_STORAGE_KEY="$(az keyvault secret show --vault-name "${KEY_VAULT}" -n staging-storage-key --query value -o tsv)"
  fi
  {
    printf 'ARCHIVE_STORE=azuresql\nLDM_NAMESPACE=%s\nLDM_RUN_TOKEN=%s\nLDM_HOST=eks\n' "${TOKEN}" "${RUN}"
    printf 'DB2_HOST=%s.%s.svc.cluster.local\nDB2_PORT=50000\nDB2_DATABASE=%s\nDB2_USER=db2inst1\nDB2_PASSWORD=%s\n' \
      "${DB2_RELEASE}" "${NS}" "${DB2_DB}" "${DB2_PASSWORD}"
    printf 'LDM_S3_BUCKET=%s\nLDM_S3_PREFIX=%s/\n' "${DEMO_BUCKET}" "${TOKEN}"
    printf 'AZSQL_SERVER=%s\nAZSQL_DATABASE=%s\nAZSQL_USER=%s\nAZSQL_PASSWORD=%s\nAZSQL_AUTH=sql\n' \
      "${AZSQL_SERVER}" "${AZSQL_DATABASE}" "${AZSQL_USER}" "${AZSQL_PASSWORD}"
    printf 'AZSQL_READER_USER=%s\nAZSQL_READER_PASSWORD=%s\n' "${AZSQL_READER_USER:-}" "${AZSQL_READER_PASSWORD:-}"
    printf 'AZ_STORAGE_ACCOUNT=%s\nAZ_STAGING_CONTAINER=%s\nAZ_STORAGE_KEY=%s\nAZURE_CLIENT_ID=%s\n' \
      "${AZ_STORAGE_ACCOUNT}" "${AZ_STAGING_CONTAINER}" "${AZ_STORAGE_KEY:-}" "${MI_CLIENT_ID}"
    printf 'PEER_APP_URL=https://%s\nACA_REPORT_URL=https://%s\nACA_AUDIT_URL=https://%s\n' "${BEFORE_HOST}" "${ACA_REPORT_URL}" "${ACA_AUDIT_URL}"
  } | apply_secret_from_stdin "${NS}" "${ARCHIVE_STORE_SECRET}" "${TOKEN}"
  # Secret `ldm-azure` consumed by the migration-job chart (§13.2): Key Vault values only.
  printf 'AZSQL_USER=%s\nAZSQL_PASSWORD=%s\nAZ_STORAGE_KEY=%s\nAZSQL_READER_USER=%s\nAZSQL_READER_PASSWORD=%s\n' \
    "${AZSQL_USER}" "${AZSQL_PASSWORD}" "${AZ_STORAGE_KEY:-}" "${AZSQL_READER_USER:-}" "${AZSQL_READER_PASSWORD:-}" \
    | apply_secret_from_stdin "${NS}" "${LDM_AZURE_SECRET}" "${TOKEN}"
  unset AZSQL_PASSWORD AZ_STORAGE_KEY AZSQL_READER_PASSWORD
  wire_archive_store "${NS}" || wiring_rc=$?
  # Schema + ledger bootstrap (`python -m ldm init`, §9.1). Idempotent. The
  # migration stages are started later by `make demo-migrate`.
  export LDM_JOB_IMAGE="${JOB_IMAGE}"
  run_stage_job "${TOKEN}" init "$(default_run_id)" "${TRANSCRIPT_DIR}/ldm-init.log" || wiring_rc=$?
  stage_end "${wiring_rc}"
fi

# --- summary ------------------------------------------------------------------------------------
echo
dlog "namespace   : ${NS}   (expires ${EXPIRES})"
dlog "web         : https://${WEB_HOST}"
dlog "api         : https://${API_HOST}"
dlog "db2         : ${DB2_RELEASE}.${NS}.svc.cluster.local:50000/${DB2_DB}  (ARCHIVE_STORE=$([ "${WANT_AZURE}" = "true" ] && echo azuresql || echo db2))"
[ "${WANT_AZURE}" = "true" ] && dlog "azure       : $(azure_rg "${TOKEN}") / ${AZSQL_SERVER:-?} / ${AZSQL_DATABASE:-?}   peer=https://${BEFORE_HOST}"
[ "${WANT_AZURE}" = "true" ] && dlog "next        : make demo-migrate NS=${TOKEN} RUN_ID=$(default_run_id)"
print_timing_table
dlog "transcript  : ${TRANSCRIPT}"
exit "${wiring_rc}"
