#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks - Per-Tenant Scale-to-Zero (cost control)
#
# Between demo sessions, scale a tenant's compute to zero while KEEPING the
# namespace, config/secrets, per-tenant Redis/MeiliSearch data and RDS database
# intact — compute cost drops to ~0, spin-up is a single command.
#
# Usage:
#   ./scripts/tenant-scale.sh <ATTENDEE_ID> down   # scale all deployments to 0
#   ./scripts/tenant-scale.sh <ATTENDEE_ID> up     # scale all deployments to 1
# ------------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/tenant-common.sh
source "${SCRIPT_DIR}/lib/tenant-common.sh"

ATTENDEE_ID="${1:-}"
DIRECTION="${2:-}"
[ -n "${ATTENDEE_ID}" ] && [ -n "${DIRECTION}" ] || { err "Usage: $0 <ATTENDEE_ID> <up|down>"; exit 1; }
require_bins kubectl
NS="$(tenant_namespace "${ATTENDEE_ID}")"
kubectl get ns "${NS}" >/dev/null 2>&1 || { err "Namespace ${NS} not found."; exit 1; }

case "${DIRECTION}" in
  down) replicas=0 ;;
  up)   replicas=1 ;;
  *)    err "Direction must be 'up' or 'down'"; exit 1 ;;
esac

log "Scaling all deployments in ${NS} to ${replicas}..."
kubectl -n "${NS}" scale deployment --all --replicas="${replicas}"
kubectl -n "${NS}" get deploy
