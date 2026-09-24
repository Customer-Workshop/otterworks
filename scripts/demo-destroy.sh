#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks legacy-data-migration demo — tear one namespace down (ops unit).
#
#   scripts/demo-destroy.sh <token> [--dry-run] [--skip-verify]
#   scripts/demo-destroy.sh verify <token>        (Makefile demo-verify-clean)
#
# Order (§12.1): Azure terraform destroy (when its state or resource group
# exists) -> helm uninstall migration jobs + db2-archive -> the existing
# tenant teardown (scripts/teardown-tenant.sh: namespace, RDS db, IRSA trust)
# -> delete the S3 prefix -> demo-aws terraform destroy -> VERIFY nothing
# tagged namespace=<token> survives in AWS, Azure or Kubernetes. Exit 1 if
# anything survives. Transcript: .demo/<token>/destroy-<ts>.log.
# Idempotent: rerunning against a clean token is a series of no-ops.
# ------------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/demo-common.sh
source "${SCRIPT_DIR}/lib/demo-common.sh"

usage() {
  cat <<EOF
Usage: $0 <token> [--dry-run] [--skip-verify]
       $0 verify <token>          # only the survivor check (make demo-verify-clean)
Destroys everything tagged/labelled namespace=<token>: Azure Terraform, Helm releases,
the OtterWorks tenant, the S3 prefix and the demo-aws Terraform; then verifies.
DRY_RUN=1 / --dry-run prints every mutating command instead of running it.
EOF
}

MODE="destroy"
[ "${1:-}" = "verify" ] && { MODE="verify"; shift; }
[ $# -ge 1 ] || { usage; exit 2; }
TOKEN="$1"; shift
SKIP_VERIFY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     DRY_RUN=1; shift ;;
    --skip-verify) SKIP_VERIFY=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) derr "unknown argument: $1"; usage; exit 2 ;;
  esac
done
export DRY_RUN

validate_token "${TOKEN}"
NS="$(demo_namespace "${TOKEN}")"
RG="$(azure_rg "${TOKEN}")"
require_bins aws kubectl helm terraform jq

if [ "${MODE}" = "verify" ]; then
  aws_account_id
  verify_clean "${TOKEN}" && { dlog "${TOKEN}: clean"; exit 0; }
  die "${TOKEN}: survivors found" 1
fi

start_transcript "${TOKEN}" destroy
dlog "destroy token=${TOKEN} namespace=${NS} dry_run=${DRY_RUN} ($(now_utc))"
aws_account_id; ensure_kubeconfig
DEMO_BUCKET="$(demo_s3_bucket "${TOKEN}")"

# --- 1. Azure ----------------------------------------------------------------------
stage_begin "azure terraform destroy"
azure_rc=0
if az_available; then
  az_login
  RG_EXISTS="$( [ "${DRY_RUN}" = "1" ] && echo unknown || az group exists -n "${RG}" -o tsv 2>/dev/null || echo false)"
  STATE_EXISTS="false"
  if [ "${DRY_RUN}" != "1" ] && [ -n "${TFSTATE_AZ_ACCOUNT:-}" ]; then
    STATE_EXISTS="$(az storage blob exists --auth-mode login --account-name "${TFSTATE_AZ_ACCOUNT}" \
      -c "${TFSTATE_AZ_CONTAINER:-tfstate}" -n "$(azure_tfstate_key "${TOKEN}")" --query exists -o tsv 2>/dev/null || echo false)"
  fi
  dlog "azure: resource group exists=${RG_EXISTS}, state blob exists=${STATE_EXISTS}"
  if [ "${RG_EXISTS}" != "false" ] || [ "${STATE_EXISTS}" = "true" ]; then
    if [ -d "${AZURE_TF_DIR}" ] && [ -n "${TFSTATE_AZ_ACCOUNT:-}" ] && [ -n "${TFSTATE_AZ_RESOURCE_GROUP:-}" ]; then
      tf_init "${TOKEN}" "${AZURE_TF_DIR}" azure_backend_args
      TFVARS="${TRANSCRIPT_DIR}/azure.auto.tfvars.json"
      DESTROY_ARGS=(-var "namespace=${TOKEN}" -var "run_token=$(token_run "${TOKEN}")" -var "state=$(token_state "${TOKEN}")" -var "expires=$(now_utc)" -var "location=${AZURE_LOCATION:-centralus}")
      [ -f "${TFVARS}" ] && DESTROY_ARGS=(-var-file="${TFVARS}")
      export TF_VAR_registry_username="AWS" TF_VAR_registry_password="unused-on-destroy"
      tf "${TOKEN}" "${AZURE_TF_DIR}" destroy -input=false -auto-approve "${DESTROY_ARGS[@]}" || azure_rc=$?
      unset TF_VAR_registry_password
    else
      dwarn "Azure Terraform root or TFSTATE_AZ_* not available; falling back to resource-group delete"
    fi
    # Belt and braces: whatever Terraform did not track (or if its state is gone).
    if [ "${DRY_RUN}" = "1" ] || [ "$(az group exists -n "${RG}" -o tsv 2>/dev/null)" = "true" ]; then
      run az group delete -n "${RG}" --yes --no-wait -o none || azure_rc=$?
    fi
    # Key Vault soft-delete would otherwise keep the name reserved for 90 days.
    if [ "${DRY_RUN}" != "1" ]; then
      for kv in $(az keyvault list-deleted --query "[?tags.namespace=='${TOKEN}'].name" -o tsv 2>/dev/null); do
        run az keyvault purge -n "${kv}" -o none || dwarn "could not purge deleted key vault ${kv}"
      done
    fi
  else
    dlog "azure: nothing to destroy for ${TOKEN}"
  fi
elif [ "$(token_wants_azure "${TOKEN}")" = "true" ]; then
  derr "${TOKEN} is Azure-backed (overlay azure: true or an after-token) but AZURE_* credentials are not set; refusing to certify"
  azure_rc=1
else
  dwarn "AZURE_* credentials not set; skipping Azure destroy (before-token, no Azure objects)"
fi
stage_end "${azure_rc}"

# --- 2. Helm releases ----------------------------------------------------------------
stage_begin "helm uninstall"
helm_rc=0
if [ "${DRY_RUN}" = "1" ] || kubectl get ns "${NS}" >/dev/null 2>&1; then
  # Migration Jobs are templated, not released: delete by label.
  run kubectl -n "${NS}" delete jobs -l "app.kubernetes.io/part-of=otterworks-ldm" --ignore-not-found --wait=false || helm_rc=$?
  if [ "${DRY_RUN}" = "1" ] || helm -n "${NS}" status "${DB2_RELEASE}" >/dev/null 2>&1; then
    run helm -n "${NS}" uninstall "${DB2_RELEASE}" --wait --timeout 10m || helm_rc=$?
  fi
  if [ "${DRY_RUN}" != "1" ]; then
    for rel in $(helm -n "${NS}" list -q -l "app.kubernetes.io/part-of=otterworks-ldm" 2>/dev/null); do
      run helm -n "${NS}" uninstall "${rel}" --wait --timeout 5m || helm_rc=$?
    done
  else
    dlog "[dry-run] would uninstall releases labelled app.kubernetes.io/part-of=otterworks-ldm"
  fi
else
  dlog "namespace ${NS} absent; no Helm releases to remove"
fi
# The static PV bound to the EBS volume is cluster-scoped: a Released PV survives
# namespace deletion, so it is removed regardless of whether the namespace exists.
if [ "${DRY_RUN}" = "1" ]; then
  dlog "[dry-run] kubectl delete pv -l demo/namespace=${TOKEN}"
else
  if pvs="$(demo_pvs "${TOKEN}")"; then
    for pv in ${pvs}; do
      run kubectl delete "${pv}" --ignore-not-found --wait=false || helm_rc=$?
    done
  else
    helm_rc=1
  fi
fi
stage_end "${helm_rc}"

# --- 3. Tenant teardown (existing path) ------------------------------------------------
stage_begin "teardown-tenant"
tenant_rc=0
if [ "${DRY_RUN}" = "1" ] || kubectl get ns "${NS}" >/dev/null 2>&1 || [ -n "${DB_PASSWORD:-}" ]; then
  run "${SCRIPT_DIR}/teardown-tenant.sh" "${TOKEN}" || tenant_rc=$?
else
  dlog "namespace ${NS} absent and DB_PASSWORD unset; skipping teardown-tenant.sh"
fi
stage_end "${tenant_rc}"

# --- 4. S3 prefix + demo-aws Terraform ----------------------------------------------------
stage_begin "aws cleanup (s3 prefix, demo-aws terraform)"
aws_rc=0
if [ "${DRY_RUN}" = "1" ] || aws s3api head-bucket --bucket "${DEMO_BUCKET}" >/dev/null 2>&1; then
  run aws s3 rm "s3://${DEMO_BUCKET}/${TOKEN}/" --recursive --only-show-errors || aws_rc=$?
fi
# Shared tenant buckets (Tier A prefixes) - the tenant's uploads live under <token>/.
for b in $(aws s3api list-buckets --query "Buckets[?starts_with(Name, 'otterworks-')].Name" --output text 2>/dev/null | tr '\t' '\n' | grep -v "^${DEMO_BUCKET}$" | grep -v terraform-state || true); do
  [ "${DRY_RUN}" = "1" ] && continue
  if [ "$(aws s3api list-objects-v2 --bucket "${b}" --prefix "${TOKEN}/" --max-keys 1 --query 'KeyCount' --output text 2>/dev/null)" = "1" ]; then
    run aws s3 rm "s3://${b}/${TOKEN}/" --recursive --only-show-errors || aws_rc=$?
  fi
done
if [ -d "${DEMO_AWS_TF_DIR}" ]; then
  tf_init "${TOKEN}" "${DEMO_AWS_TF_DIR}" aws_backend_args
  tf "${TOKEN}" "${DEMO_AWS_TF_DIR}" destroy -input=false -auto-approve \
    -var "namespace=${TOKEN}" -var "expires=$(now_utc)" -var "aws_region=${AWS_REGION}" -var "eks_cluster=${EKS_CLUSTER}" || aws_rc=$?
fi
# Anything tagged but untracked (e.g. a volume Terraform lost): delete by tag.
if [ "${DRY_RUN}" != "1" ]; then
  for arn in $(aws_live_resources_with_namespace "${TOKEN}"); do
    case "${arn}" in
      arn:aws:ec2:*:volume/*) run aws ec2 delete-volume --region "${AWS_REGION}" --volume-id "${arn##*/}" || aws_rc=$? ;;
      arn:aws:ecr:*:repository/*) run aws ecr delete-repository --region "${AWS_REGION}" --repository-name "${arn#*repository/}" --force || aws_rc=$? ;;
      arn:aws:s3:::*) run aws s3 rb "s3://${arn#arn:aws:s3:::}" --force || aws_rc=$? ;;
      *) dwarn "untracked survivor left for manual review: ${arn}" ;;
    esac
  done
fi
stage_end "${aws_rc}"

# --- 5. Verify --------------------------------------------------------------------------------
verify_rc=0
if [ "${SKIP_VERIFY}" = "1" ]; then dwarn "verification skipped (--skip-verify)"
else
  stage_begin "verify clean"
  if [ "${DRY_RUN}" != "1" ] && az_available && [ "$(az group exists -n "${RG}" -o tsv 2>/dev/null)" = "true" ]; then
    dlog "waiting for Azure resource group ${RG} deletion..."
    az group wait -n "${RG}" --deleted --timeout 1800 2>/dev/null || true
  fi
  verify_clean "${TOKEN}" || verify_rc=$?
  stage_end "${verify_rc}"
fi

print_timing_table
dlog "transcript: ${TRANSCRIPT}"
if [ "${verify_rc}" -ne 0 ]; then die "${TOKEN}: resources survived destroy (see above)" 1; fi
[ "${azure_rc}${helm_rc}${tenant_rc}${aws_rc}" = "0000" ] || dwarn "some stages reported errors but verification found no survivors"
dlog "${TOKEN}: destroyed and verified clean"
