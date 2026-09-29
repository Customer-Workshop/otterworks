#!/usr/bin/env bash
# One command to rebuild BOTH namespaces of a run from scratch and re-seed them.
# The after side is delegated to ticketing/deploy/after/deploy.sh once it exists.
#   usage: reset.sh <token>
source "$(dirname "$0")/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
start_transcript "${TOKEN}" reset
SECONDS=0
ensure_kubeconfig
for ns in "$(ns_before "${TOKEN}")" "$(ns_after "${TOKEN}")"; do
  if kubectl get ns "${ns}" >/dev/null 2>&1; then log "deleting ${ns}"; kubectl delete ns "${ns}" --wait=true --timeout=10m; fi
done
"${TKT_ROOT}/scripts/deploy-before.sh" "${TOKEN}"
if [ -x "${TKT_ROOT}/deploy/after/deploy.sh" ]; then
  "${TKT_ROOT}/deploy/after/deploy.sh" "${TOKEN}"
else
  log "after side not built yet (ticketing/deploy/after/deploy.sh absent) — before only"
fi
[ -x "${TKT_ROOT}/load/seed.sh" ] && "${TKT_ROOT}/load/seed.sh" "${TOKEN}"
log "reset complete in ${SECONDS}s; replica counts at rest:"
"${TKT_ROOT}/scripts/status.sh" "${TOKEN}"
