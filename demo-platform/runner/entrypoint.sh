#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks Demo Platform — runner entrypoint
#
# This image is launched as a Kubernetes Job by the ops dashboard (namespace
# otterworks-platform). It carries the repo + toolchain (aws/kubectl/helm/
# terraform/jq/psql) and executes ONE mutating operation, then exits.
#
# It is deliberately thin glue: the real work is done by the EXISTING tenant
# tooling in ../scripts (deploy-tenant.sh / teardown-tenant.sh / inject-bug.sh)
# and the reaper in ../reaper/reaper.sh. This entrypoint only:
#   1. checks out the requested OtterWorks git branch (TENANT_BRANCH),
#   2. transitions status in the control table (deploying -> active | error),
#   3. runs the requested op via the existing scripts,
#   4. records the resolved coordinates (url/api_url/db_name/namespace/expires)
#      and appends AUDIT events.
#
# Environment (control-plane metadata; NON-secret):
#   OP            deploy | teardown | inject | reset | reap        (required)
#   TENANT_ID     attendee id (required for deploy/teardown/inject/reset)
#   TIER          A | B                                            (default A)
#   TTL           e.g. 8h, 30m, 2d                                 (default 8h)
#   IMAGE_TAG     optional pinned image tag
#   HOST_SUFFIX   ingress host suffix              (default demo.otterworks.xyz)
#   SCENARIO      bug-catalog scenario (for OP=inject)
#   TENANT_BRANCH git branch to check out (e.g. workshop-<id>)
#   CONTROL_TABLE DynamoDB control table         (default otterworks-demo-control)
#   AWS_REGION    (default us-east-1)   EKS_CLUSTER (default otterworks-dev)
#   REPO_DIR      checked-out repo path                   (default /workspace)
#   REPO_REMOTE   git remote name                         (default origin)
#   ACTOR         audit actor label                       (default runner)
#
# Secrets (from Kubernetes Secret refs in the Job spec — env only, NEVER argv):
#   DB_PASSWORD, JWT_SECRET, SECRET_KEY_BASE
#
# This script never echoes secret values and never passes them on a command line;
# the underlying scripts read them straight from the environment.
# ------------------------------------------------------------------------------
set -euo pipefail

REPO_DIR="${REPO_DIR:-/workspace}"
REPO_REMOTE="${REPO_REMOTE:-origin}"
CONTROL_TABLE="${CONTROL_TABLE:-otterworks-demo-control}"
AWS_REGION="${AWS_REGION:-us-east-1}"
EKS_CLUSTER="${EKS_CLUSTER:-otterworks-dev}"
HOST_SUFFIX="${HOST_SUFFIX:-demo.otterworks.xyz}"
TIER="${TIER:-A}"
TTL="${TTL:-8h}"
OP="${OP:-}"

log()  { echo "[runner] $*"; }
err()  { echo "[runner] ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

# --- git checkout of the requested branch (deploy uses the tenant's branch) ----
checkout_branch() {
  [ -n "${TENANT_BRANCH:-}" ] || { log "no TENANT_BRANCH set; using image's bundled checkout"; return 0; }
  log "checking out branch ${TENANT_BRANCH} in ${REPO_DIR}"
  git config --global --add safe.directory "${REPO_DIR}" >/dev/null 2>&1 || true
  ( cd "${REPO_DIR}" \
    && git fetch --prune "${REPO_REMOTE}" >/dev/null 2>&1 \
    && ( git checkout "${TENANT_BRANCH}" >/dev/null 2>&1 \
         || git checkout -b "${TENANT_BRANCH}" "${REPO_REMOTE}/${TENANT_BRANCH}" >/dev/null 2>&1 ) \
    && git reset --hard "${REPO_REMOTE}/${TENANT_BRANCH}" >/dev/null 2>&1 ) \
    || err "branch checkout of ${TENANT_BRANCH} failed; continuing with current tree"
}

# Convert a compact TTL (8h/30m/2d) to an absolute expiry epoch. Pure integer
# arithmetic so it works with busybox `date` (no GNU `date -d` needed).
expiry_epoch() {
  local ttl="$1" num unit mult now
  num="${ttl%%[!0-9]*}"; unit="${ttl##*[0-9]}"
  [ -n "${num}" ] || die "invalid TTL '${ttl}'"
  case "${unit}" in
    h|H|"") mult=3600 ;;
    m|M)    mult=60 ;;
    d|D)    mult=86400 ;;
    *)      die "invalid TTL unit in '${ttl}' (use h, m, or d)" ;;
  esac
  now="$(date -u +%s)"
  echo $(( now + num * mult ))
}

run_deploy() {
  [ -n "${TENANT_ID:-}" ] || die "OP=deploy requires TENANT_ID"
  : "${DB_PASSWORD:?OP=deploy requires DB_PASSWORD (from Secret)}"
  local sid ns db url api_url exp
  sid="$(sanitize_id "${TENANT_ID}")"
  ns="$(tenant_namespace "${TENANT_ID}")"
  db="$(tenant_db_name "${TENANT_ID}")"
  url="https://t-${sid}.${HOST_SUFFIX}"
  api_url="https://api-t-${sid}.${HOST_SUFFIX}"
  exp="$(expiry_epoch "${TTL}")"

  ctl_update_status "${TENANT_ID}" deploying
  ctl_audit "${TENANT_ID}" checkout "tier=${TIER} ttl=${TTL} branch=${TENANT_BRANCH:-} ns=${ns}"

  local args=(--tier "${TIER}" --ttl "${TTL}" --host-suffix "${HOST_SUFFIX}")
  [ -n "${IMAGE_TAG:-}" ] && args+=(--image-tag "${IMAGE_TAG}")
  # Secrets (DB_PASSWORD/JWT_SECRET/SECRET_KEY_BASE) are read from the env by the
  # script; they are NOT placed on this argv.
  if "${REPO_DIR}/scripts/deploy-tenant.sh" "${TENANT_ID}" "${args[@]}"; then
    ctl_set_active "${TENANT_ID}" "${url}" "${api_url}" "${db}" "${ns}" "${exp}"
    ctl_audit "${TENANT_ID}" deploy_ok "url=${url}"
    log "deploy complete for ${TENANT_ID} (${ns})"
  else
    ctl_update_status "${TENANT_ID}" error
    ctl_audit "${TENANT_ID}" deploy_fail "deploy-tenant.sh returned non-zero"
    die "deploy failed for ${TENANT_ID}"
  fi
}

run_teardown() {
  [ -n "${TENANT_ID:-}" ] || die "OP=teardown requires TENANT_ID"
  ctl_update_status "${TENANT_ID}" draining
  # teardown-tenant.sh reads DB_PASSWORD from the env to drop the per-tenant DB.
  "${REPO_DIR}/scripts/teardown-tenant.sh" "${TENANT_ID}" \
    || err "teardown-tenant.sh reported issues (continuing to free the id)"
  ctl_update_status "${TENANT_ID}" free
  # Release the reservation lock so the id is immediately re-checkout-able
  # (otherwise a new checkout waits for the lock's ~15min DynamoDB TTL).
  ctl_release_lock "${TENANT_ID}"
  ctl_audit "${TENANT_ID}" checkin "torn down and freed"
  log "teardown complete for ${TENANT_ID}"
}

run_inject() {
  [ -n "${TENANT_ID:-}" ] || die "OP=inject requires TENANT_ID"
  [ -n "${SCENARIO:-}" ]  || die "OP=inject requires SCENARIO"
  local args=("${TENANT_ID}" "${SCENARIO}")
  [ -n "${IMAGE_TAG:-}" ] && args+=(--image-tag "${IMAGE_TAG}")
  "${REPO_DIR}/scripts/inject-bug.sh" "${args[@]}"
  ctl_audit "${TENANT_ID}" inject "scenario=${SCENARIO}"
  log "inject '${SCENARIO}' applied to ${TENANT_ID}"
}

run_reset() {
  [ -n "${TENANT_ID:-}" ] || die "OP=reset requires TENANT_ID"
  "${REPO_DIR}/scripts/inject-bug.sh" "${TENANT_ID}" reset
  ctl_audit "${TENANT_ID}" reset "cleared chaos flags"
  log "reset complete for ${TENANT_ID}"
}

run_reap() {
  log "delegating to reaper v2"
  exec "${REPO_DIR}/demo-platform/reaper/reaper.sh"
}

main() {
  [ -n "${OP}" ] || die "OP is required (deploy|teardown|inject|reset|reap)"
  command -v aws >/dev/null || die "aws CLI not found in image"
  command -v jq  >/dev/null || die "jq not found in image"

  checkout_branch

  # Shared naming + control-table helpers (from the checked-out repo).
  # shellcheck source=/dev/null
  source "${REPO_DIR}/scripts/lib/tenant-common.sh"
  # shellcheck source=/dev/null
  source "${REPO_DIR}/demo-platform/lib/control-common.sh"

  # Build kubeconfig for in-cluster ops (deploy/teardown scripts also do this,
  # but inject/reset/reap rely on it being present).
  aws eks update-kubeconfig --name "${EKS_CLUSTER}" --region "${AWS_REGION}" >/dev/null 2>&1 || true

  case "${OP}" in
    deploy)   run_deploy ;;
    teardown) run_teardown ;;
    inject)   run_inject ;;
    reset)    run_reset ;;
    reap)     run_reap ;;
    *)        die "unknown OP '${OP}' (deploy|teardown|inject|reset|reap)" ;;
  esac
}

main "$@"
