#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks legacy-data-migration demo — bring up one namespace (ops unit).
#
#   scripts/deploy-demo.sh <token> [--ttl 72h] [--image-tag TAG]
#                          [--host-suffix otterworks.app] [--dry-run]
#   scripts/deploy-demo.sh up <token> ...        (Makefile form, §12.1)
#
# <token> = <run>-<before|after>, e.g. d24-before. Always:
#   1. demo-aws Terraform      - source-estate EBS volume, S3 bucket, ECR repo (tagged)
#   2. deploy-tenant.sh        - the ordinary OtterWorks tenant (existing path)
#   3. source chart, by the overlay's source.driver (default db2):
#        db2    - db2-archive chart: Db2 StatefulSet + seed hook, DB <RUN>B|<RUN>A
#        oracle - oracle-archive chart: Oracle Free 23ai StatefulSet (ECR mirror of the
#                 digest-pinned image) + seed hook over SQL*Net from the ldm job image
#   4. wiring                  - archive-store-credentials, ARCHIVE_STORE=<driver>
# When the token's overlay says migrate: true with azure: false (the default
# d24-after: PostgreSQL + S3 + Spark local mode, nothing provisioned in Azure):
#   5. wiring                  - the tenant's existing RDS database + the token's
#                                S3 prefix -> Secrets, ARCHIVE_STORE=postgresql,
#                                PEER_APP_URL=<before host>, `ldm init` Job.
# When the overlay says azure: true (optional rehearsal, r2-after):
#   5. azure Terraform         - per-namespace state key, generated var file
#   6. wiring                  - Azure outputs -> Secrets, ARCHIVE_STORE=azuresql, ...
# The migration itself is NOT started here (`make demo-migrate NS=<token> RUN_ID=<id>`).
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
Env: DB_PASSWORD (RDS master, for deploy-tenant.sh and the PostgreSQL target), AWS creds; only for
     azure: true overlays also AZURE_CLIENT_ID/SECRET/TENANT_ID/SUBSCRIPTION_ID and TFSTATE_AZ_*.
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
require_overlay "${TOKEN}"
RUN="$(token_run "${TOKEN}")"; STATE="$(token_state "${TOKEN}")"
NS="$(demo_namespace "${TOKEN}")"
SOURCE_DRIVER="$(token_source_driver "${TOKEN}")"
DB2_DB="$(db2_db_name "${TOKEN}")"
EXPIRES="$(ttl_to_expires "${TTL}")"
WANT_AZURE="$(token_wants_azure "${TOKEN}")"
WANT_MIGRATE="$(token_wants_migrate "${TOKEN}")"
WEB_HOST="$(demo_web_host "${TOKEN}")"; API_HOST="$(demo_api_host "${TOKEN}")"
BEFORE_HOST="$(demo_web_host "${RUN}-before")"

require_bins aws kubectl helm terraform jq
require_dir "${DEMO_AWS_TF_DIR}" "demo-aws Terraform root" ops
case "${SOURCE_DRIVER}" in
  db2)    require_chart "${DB2_CHART_DIR}" source ;;
  oracle) require_chart "${ORACLE_CHART_DIR}" source; require_chart "${JOB_CHART_DIR}" job ;;  # seed hook runs the job image
esac
[ "${WANT_MIGRATE}" = "true" ] && require_chart "${JOB_CHART_DIR}" job
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
  ensure_db_password
  : "${DB_PASSWORD:?DB_PASSWORD must be set (RDS master password, or readable from Secrets Manager ${RDS_MASTER_SECRET_ID}; see docs/demos/${DEMO_NAME}.md)}"
fi

start_transcript "${TOKEN}" deploy
dlog "token=${TOKEN} run=${RUN} state=${STATE} namespace=${NS} source=${SOURCE_DRIVER} db2=${DB2_DB} expires=${EXPIRES} migrate=${WANT_MIGRATE} azure=${WANT_AZURE} dry_run=${DRY_RUN}"
aws_account_id; ensure_kubeconfig
DEMO_BRANCH="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "demo/${DEMO_NAME}")"
dlog "tags: $(demo_tags_kv "${TOKEN}" "${EXPIRES}")"
LABELS_KV="$(demo_k8s_labels "${TOKEN}")"

# --- 1. demo-aws Terraform ---------------------------------------------------------
stage_begin "aws terraform (demo-aws)"
tf_init "${TOKEN}" "${DEMO_AWS_TF_DIR}" aws_backend_args
demo_aws_tf_vars "${TOKEN}" "${EXPIRES}"
tf "${TOKEN}" "${DEMO_AWS_TF_DIR}" apply -input=false -auto-approve "${DEMO_AWS_TF_VARS[@]}"
DB2_VOLUME_ID="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" db2_volume_id)"
DB2_VOLUME_AZ="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" db2_volume_az)"
DEMO_BUCKET="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" bucket_name)"
JOB_ROLE_ARN="$(tf_output "${TOKEN}" "${DEMO_AWS_TF_DIR}" job_role_arn)"
[ -n "${DEMO_BUCKET}" ] || DEMO_BUCKET="$(demo_s3_bucket "${TOKEN}")"
stage_end 0

# --- 2. tenant via deploy-tenant.sh --------------------------------------------------
stage_begin "deploy-tenant"
# Registered before the namespace exists: the platform reaper's orphan sweep runs every 15 min
# with a 5-min grace, less than deploy-tenant + Db2 seed take.
if [ "${DRY_RUN}" = "1" ]; then dlog "[dry-run] would register TENANT#${TOKEN} (persistent) in ${DEMO_CONTROL_TABLE}"
else register_control_tenant "${TOKEN}" "${EXPIRES}"; dlog "registered TENANT#${TOKEN} in ${DEMO_CONTROL_TABLE} (persistent until demo-destroy)"; fi
# --branch makes deploy-tenant prefer this token's own build (tenant-<token>) for the services the
# branch touched (report/audit/admin-dashboard) and the golden image for everything else.
DT_ARGS=("${TOKEN}" --ttl "${TTL}" --host-suffix "${DEMO_HOST_SUFFIX}" --profile "${PROFILE}" --branch "${DEMO_BRANCH}")
[ -n "${IMAGE_TAG}" ] && DT_ARGS+=(--image-tag "${IMAGE_TAG}")
run env HOST_SUFFIX="${DEMO_HOST_SUFFIX}" "${SCRIPT_DIR}/deploy-tenant.sh" "${DT_ARGS[@]}"
# Demo labels on top of the tenant labels/expiry annotation deploy-tenant sets (§3.3).
# shellcheck disable=SC2086
run kubectl label namespace "${NS}" --overwrite ${LABELS_KV}
run kubectl annotate namespace "${NS}" --overwrite "demo/expires=${EXPIRES}"
# The tenant ingress only routes the SPA and the gateway; the presenter's Migration report
# lives in the Angular admin dashboard, so the demo adds admin-t-<token> on the same shared
# ingress (ClusterIP behind ingress-nginx, Route53 record from demo-aws).
if [ "${DRY_RUN}" = "1" ]; then dlog "[dry-run] would apply tenant-ingress-admin for admin-t-${TOKEN}.${DEMO_HOST_SUFFIX}"
else kubectl apply -n "${NS}" -f - <<YAML
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tenant-ingress-admin
spec:
  ingressClassName: nginx
  rules:
    - host: admin-t-${TOKEN}.${DEMO_HOST_SUFFIX}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: { name: admin-dashboard, port: { number: 80 } }
YAML
fi
# deploy-tenant sizes tenant-quota for the app alone (12 CPU / 20Gi of limits); the demo adds
# Db2 (2/4Gi), its seed Job (2/2Gi) and the migration Job (1/1Gi) in the same namespace.
run kubectl -n "${NS}" patch resourcequota tenant-quota --type merge -p \
  '{"spec":{"hard":{"limits.cpu":"18","limits.memory":"28Gi","requests.cpu":"6","requests.memory":"12Gi","pods":"50"}}}'
# The token's S3 prefix: an explicit prefix marker so the bucket layout is
# visible (and deletable by prefix) before the first unload lands.
run aws s3api put-object --bucket "${DEMO_BUCKET}" --key "${TOKEN}/" --content-length 0
stage_end 0

# --- 3. source archive store + seed ------------------------------------------------------------
# The seed hook waits for the seed Job the chart's post-install hook created; the Job is
# idempotent (tables already at their SEED-SPEC count are skipped) so `helm upgrade` is safe.
wait_for_seed_job() {
  local release="$1" what="$2" job
  [ "${DRY_RUN}" = "1" ] && return 0
  job="$(kubectl -n "${NS}" get jobs -l "app.kubernetes.io/instance=${release}" -o name 2>/dev/null | head -1 || true)"
  [ -n "${job}" ] || die "chart has initJob.enabled=true but no Job labelled app.kubernetes.io/instance=${release} exists; ${what} is not seeded"
  if ! kubectl -n "${NS}" wait --for=condition=complete "${job}" --timeout=90m; then
    kubectl -n "${NS}" logs "${job}" --tail=40 2>/dev/null || true
    die "seed job ${job} did not complete; ${what} is empty or partial - not continuing"
  fi
}
SOURCE_ENV=""   # <DRIVER>_HOST/... lines the app + job read (CONTRACTS §9.2, §10.4)
if [ "${SOURCE_DRIVER}" = "oracle" ]; then
stage_begin "oracle seed"
ensure_oracle_image
# The seeder runs from the token's ldm job image (python-oracledb thin mode + migration/source/seed).
ensure_ldm_job_image "${TOKEN}"
ORACLE_JOB_IMAGE="$(ldm_job_image "${TOKEN}")"
ORACLE_PASSWORD="$(secret_value "${NS}" "${ORACLE_CREDENTIALS_SECRET}" ORACLE_PASSWORD)"
if [ -z "${ORACLE_PASSWORD}" ]; then
  # Oracle passwords: start with a letter, no shell metacharacters (the image passes them through sqlplus).
  ORACLE_PASSWORD="Ow$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-22)"
  ORACLE_SYS_PASSWORD="Ow$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-22)"
  printf 'ORACLE_USER=%s\nORACLE_PASSWORD=%s\nORACLE_SYS_PASSWORD=%s\n' LDMUSER "${ORACLE_PASSWORD}" "${ORACLE_SYS_PASSWORD}" \
    | apply_secret_from_stdin "${NS}" "${ORACLE_CREDENTIALS_SECRET}" "${TOKEN}"
  unset ORACLE_SYS_PASSWORD
else
  dlog "reusing existing ${ORACLE_CREDENTIALS_SECRET}"
fi
ORACLE_USER="$(secret_value "${NS}" "${ORACLE_CREDENTIALS_SECRET}" ORACLE_USER)"; ORACLE_USER="${ORACLE_USER:-LDMUSER}"
ORACLE_ARGS=(--namespace "${NS}" --create-namespace=false
  --set "namespaceToken=${TOKEN}" --set "credentialsSecret=${ORACLE_CREDENTIALS_SECRET}"
  --set "pv.size=20Gi" --set "pv.volumeName=otterworks-ldm-${TOKEN}-oracle" --set "expires=${EXPIRES}"
  --set "initJob.enabled=true" --set "initJob.image.repository=${ORACLE_JOB_IMAGE%:*}" --set "initJob.image.tag=${ORACLE_JOB_IMAGE##*:}")
# The EBS volume comes from demo-aws Terraform (the token's one source-estate volume); static PV (§12.4).
[ -n "${DB2_VOLUME_ID}" ] && ORACLE_ARGS+=(--set "pv.create=true" --set "pv.volumeId=${DB2_VOLUME_ID}" --set "pv.zone=${DB2_VOLUME_AZ}")
# --wait covers the post-install seed hook too: 5.3M rows over SQL*Net from one pod take ~45 min at
# scale 1.0 on the SPOT node group, so the budget matches initJob.activeDeadlineSeconds (90 min).
# shellcheck disable=SC2086
run helm upgrade --install "${ORACLE_RELEASE}" "${ORACLE_CHART_DIR}" "${ORACLE_ARGS[@]}" --wait --timeout 90m ${ORACLE_HELM_ARGS:-}
wait_for_seed_job "${ORACLE_RELEASE}" "Oracle ${ORACLE_SERVICE}"
SOURCE_ENV="$(printf 'ORACLE_HOST=%s.%s.svc.cluster.local\nORACLE_PORT=%s\nORACLE_SERVICE=%s\nORACLE_USER=%s\nORACLE_PASSWORD=%s\n' \
  "${ORACLE_RELEASE}" "${NS}" "${ORACLE_PORT}" "${ORACLE_SERVICE}" "${ORACLE_USER}" "${ORACLE_PASSWORD}")"
stage_end 0
else
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
  --set "namespaceToken=${TOKEN}" --set "dbName=${DB2_DB}" --set "credentialsSecret=${DB2_CREDENTIALS_SECRET}"
  --set "pv.size=20Gi" --set "pv.volumeName=otterworks-ldm-${TOKEN}-db2" --set "expires=${EXPIRES}")
# The EBS volume comes from demo-aws Terraform; the chart binds it as a static PV (§12.4).
[ -n "${DB2_VOLUME_ID}" ] && DB2_ARGS+=(--set "pv.create=true" --set "pv.volumeId=${DB2_VOLUME_ID}" --set "pv.zone=${DB2_VOLUME_AZ}")
# Seed hook: the chart's post-install/upgrade init Job (§12.1 idempotent load).
CHART_HAS_SEED=0
if grep -qE '^initJob:' "${DB2_CHART_DIR}/values.yaml" 2>/dev/null; then CHART_HAS_SEED=1; DB2_ARGS+=(--set "initJob.enabled=true"); fi
# shellcheck disable=SC2086
run helm upgrade --install "${DB2_RELEASE}" "${DB2_CHART_DIR}" "${DB2_ARGS[@]}" --wait --timeout 30m ${DB2_HELM_ARGS:-}
SEED_SCRIPT="${REPO_ROOT}/migration/source/seed/load.sh"
if [ "${CHART_HAS_SEED}" = "1" ]; then
  wait_for_seed_job "${DB2_RELEASE}" "Db2 ${DB2_DB}"
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
SOURCE_ENV="$(printf 'DB2_HOST=%s.%s.svc.cluster.local\nDB2_PORT=50000\nDB2_DATABASE=%s\nDB2_USER=db2inst1\nDB2_PASSWORD=%s\n' \
  "${DB2_RELEASE}" "${NS}" "${DB2_DB}" "${DB2_PASSWORD}")"
stage_end 0
fi

# --- 4. wiring: archive-store-credentials (source) -----------------------------------------
# ARCHIVE_STORE=db2: report-service/audit-service read the Db2 estate directly on a before tenant.
# ArchiveStoreType knows off|db2|postgresql|azuresql only; an Oracle read path in those services is
# a follow-up, so an oracle before-tenant gets ARCHIVE_STORE=off (archive endpoints report the
# feature as disabled rather than a misconfigured store). The migration itself never uses them.
APP_SOURCE_STORE="${SOURCE_DRIVER}"
[ "${SOURCE_DRIVER}" = "oracle" ] && APP_SOURCE_STORE=off
wiring_rc=0
stage_begin "wiring (${SOURCE_DRIVER})"
{
  printf 'ARCHIVE_STORE=%s\nLDM_NAMESPACE=%s\nLDM_RUN_TOKEN=%s\n' "${APP_SOURCE_STORE}" "${TOKEN}" "${RUN}"
  printf '%s\n' "${SOURCE_ENV}"
  printf 'LDM_S3_BUCKET=%s\nLDM_S3_PREFIX=%s/\n' "${DEMO_BUCKET}" "${TOKEN}"
} | apply_secret_from_stdin "${NS}" "${ARCHIVE_STORE_SECRET}" "${TOKEN}"
if [ "${WANT_AZURE}" != "true" ] && [ "${WANT_MIGRATE}" != "true" ]; then wire_archive_store "${NS}" || wiring_rc=$?; fi
stage_end "${wiring_rc}"

# --- 5. PostgreSQL + S3 target (default after) ----------------------------------------------
# No new database: `ldm init` creates the mig/stg/arch schemas inside the tenant's own
# otterworks_<token> database that deploy-tenant.sh already provisioned on the shared RDS
# instance. Staging is the token's prefix of the demo bucket; the Job reaches it through
# the IRSA role from demo-aws. Nothing here touches Azure.
if [ "${WANT_MIGRATE}" = "true" ] && [ "${WANT_AZURE}" != "true" ]; then
  stage_begin "wiring (postgresql + s3)"
  load_infra_outputs
  PG_DATABASE="$(tenant_db_name "${TOKEN}")"
  if [ "${DRY_RUN}" = "1" ]; then
    RDS_HOST="${RDS_HOST:-<rds endpoint>}"; RDS_PORT="${RDS_PORT:-5432}"; DB_PASSWORD="${DB_PASSWORD:-<rds master password>}"
  else
    [ -n "${RDS_HOST:-}" ] || die "shared RDS endpoint unknown (infrastructure/terraform output rds_endpoint); cannot wire the PostgreSQL target"
  fi
  ensure_ldm_job_image "${TOKEN}"
  JOB_IMAGE="$(ldm_job_image "${TOKEN}")"
  {
    printf 'ARCHIVE_STORE=postgresql\nLDM_NAMESPACE=%s\nLDM_RUN_TOKEN=%s\nLDM_HOST=eks\n' "${TOKEN}" "${RUN}"
    printf '%s\n' "${SOURCE_ENV}"
    printf 'LDM_S3_BUCKET=%s\nLDM_S3_PREFIX=%s/\n' "${DEMO_BUCKET}" "${TOKEN}"
    printf 'PG_HOST=%s\nPG_PORT=%s\nPG_DATABASE=%s\nPG_USER=%s\nPG_PASSWORD=%s\nPG_SSLMODE=require\n' \
      "${RDS_HOST}" "${RDS_PORT}" "${PG_DATABASE}" "${DB_USER}" "${DB_PASSWORD}"
    printf 'S3_STAGING_BUCKET=%s\nAWS_REGION=%s\nLDM_JOB_ROLE_ARN=%s\n' "${DEMO_BUCKET}" "${AWS_REGION}" "${JOB_ROLE_ARN}"
    printf 'PEER_APP_URL=https://%s\n' "${BEFORE_HOST}"
  } | apply_secret_from_stdin "${NS}" "${ARCHIVE_STORE_SECRET}" "${TOKEN}"
  # Secret `ldm-postgres` consumed by the migration-job chart (§13.2).
  printf 'PG_USER=%s\nPG_PASSWORD=%s\n' "${DB_USER}" "${DB_PASSWORD}" \
    | apply_secret_from_stdin "${NS}" "${LDM_POSTGRES_SECRET}" "${TOKEN}"
  wire_archive_store "${NS}" || wiring_rc=$?
  trust_peer_tokens "${TOKEN}" || wiring_rc=$?
  export LDM_JOB_IMAGE="${JOB_IMAGE}"
  run_stage_job "${TOKEN}" init "${TOKEN}" "${TRANSCRIPT_DIR}/ldm-init.log" || wiring_rc=$?
  stage_end "${wiring_rc}"
fi

# --- 5/6. Azure (optional rehearsal overlay) --------------------------------------------------
if [ "${WANT_AZURE}" = "true" ]; then
  stage_begin "azure terraform apply"
  az_login
  tf_init "${TOKEN}" "${AZURE_TF_DIR}" azure_backend_args
  if [ "${DRY_RUN}" = "1" ]; then EGRESS_CIDRS='["0.0.0.0/32"]'; else EGRESS_CIDRS="$(discover_eks_egress_cidrs)"; fi
  [ "$(jq 'length' <<<"${EGRESS_CIDRS}")" -gt 0 ] || die "could not discover EKS egress IPs for the Azure SQL firewall rule"
  REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  # Container Apps run the exact images the tenant Deployments run; the job image is built
  # from this checkout and pushed to the token's ECR repo (created by demo-aws) if missing.
  REPORT_IMAGE="$(app_image_ref "${TOKEN}" report-service)"
  AUDIT_IMAGE="$(app_image_ref "${TOKEN}" audit-service)"
  ensure_ldm_job_image "${TOKEN}"
  JOB_IMAGE="$(ldm_job_image "${TOKEN}")"
  dlog "images: report=${REPORT_IMAGE} audit=${AUDIT_IMAGE} job=${JOB_IMAGE}"
  SESSION_LINKS="$(cat "${MANIFEST_DIR}"/sessions/*.yaml 2>/dev/null | sed -nE 's/^[[:space:]-]*url:[[:space:]]*//p' | jq -R . | jq -sc . || echo '[]')"
  TFVARS="${TRANSCRIPT_DIR}/azure.auto.tfvars.json"   # token-derived, git-ignored, no secrets
  jq -n --arg ns "${TOKEN}" --arg run "${RUN}" --arg st "${STATE}" --arg exp "${EXPIRES}" \
        --argjson cidrs "${EGRESS_CIDRS}" --arg reg "${REGISTRY}" --arg report "${REPORT_IMAGE}" --arg audit "${AUDIT_IMAGE}" --arg job "${JOB_IMAGE}" \
        --arg links "${SESSION_LINKS}" --argjson inaz "$(overlay_flag "${TOKEN}" run_job_in_azure)" \
        --arg loc "${AZURE_LOCATION:-centralus}" \
        --argjson priv "${AZURE_PRIVATE_NETWORKING:-false}" '{
          namespace:$ns, run_token:$run, state:$st, expires:$exp, owner:"otterworks-demo", location:$loc,
          private_networking:$priv, eks_egress_cidrs:$cidrs, run_job_in_azure:$inaz,
          registry_server:$reg, report_image:$report, audit_image:$audit, job_image:$job,
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
    printf '%s\n' "${SOURCE_ENV}"
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
  trust_peer_tokens "${TOKEN}" || wiring_rc=$?
  # Schema + ledger bootstrap (`python -m ldm init`, §9.1). Idempotent. The
  # migration stages are started later by `make demo-migrate`.
  export LDM_JOB_IMAGE="${JOB_IMAGE}"
  # The chart names the idempotent init Job ldm-init-<token> (no run id), so the token is the
  # run-id argument here; job_name() must produce the same name the chart renders.
  run_stage_job "${TOKEN}" init "${TOKEN}" "${TRANSCRIPT_DIR}/ldm-init.log" || wiring_rc=$?
  stage_end "${wiring_rc}"
fi

# --- summary ------------------------------------------------------------------------------------
echo
dlog "namespace   : ${NS}   (expires ${EXPIRES})"
dlog "web         : https://${WEB_HOST}"
dlog "api         : https://${API_HOST}"
ARCHIVE_STORE_KIND="${APP_SOURCE_STORE}"
[ "${WANT_MIGRATE}" = "true" ] && ARCHIVE_STORE_KIND=postgresql
[ "${WANT_AZURE}" = "true" ] && ARCHIVE_STORE_KIND=azuresql
if [ "${SOURCE_DRIVER}" = "oracle" ]; then
  dlog "oracle      : ${ORACLE_RELEASE}.${NS}.svc.cluster.local:${ORACLE_PORT}/${ORACLE_SERVICE}  (ARCHIVE_STORE=${ARCHIVE_STORE_KIND})"
else
  dlog "db2         : ${DB2_RELEASE}.${NS}.svc.cluster.local:50000/${DB2_DB}  (ARCHIVE_STORE=${ARCHIVE_STORE_KIND})"
fi
[ "${ARCHIVE_STORE_KIND}" = "postgresql" ] && dlog "postgresql  : ${RDS_HOST:-?}:${RDS_PORT:-5432}/${PG_DATABASE:-?}  s3://${DEMO_BUCKET}/${TOKEN}/  (Spark local[*] in the Job)"
[ "${WANT_AZURE}" = "true" ] && dlog "azure       : $(azure_rg "${TOKEN}") / ${AZSQL_SERVER:-?} / ${AZSQL_DATABASE:-?}   peer=https://${BEFORE_HOST}"
[ "${WANT_AZURE}" = "true" ] && dlog "next        : make demo-migrate NS=${TOKEN} RUN_ID=$(default_run_id)"
print_timing_table
dlog "transcript  : ${TRANSCRIPT}"
exit "${wiring_rc}"
