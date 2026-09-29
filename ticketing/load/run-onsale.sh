#!/usr/bin/env bash
# Fire the on-sale at both hosts at once: one in-cluster k6 Job (image …/ticketing/k6:v1.8.1) running
# load/onsale.js against <token>-before and <token>-after through the shared ingress.
#   usage: load/run-onsale.sh <token>
#   knobs (env): RAMP=60s PEAK=600 (orders/min per side) DURATION=120s RAMPDOWN=30s MAX_VUS=300
#                PERFORMANCES=24 QUANTITY=2 RUN_ID=<utc timestamp>
# Output: ticketing/.runs/<token>/onsale-<run_id>.{log,json} (+ onsale-latest.json) and ConfigMap
# <token>-onsale-summary in <token>-after (keys summary.json, run_id) for the verify stage.
source "$(dirname "$0")/../scripts/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
aws_account_id; ensure_kubeconfig
NS="$(ns_after "${TOKEN}")"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dt%H%M%S)}"
[[ "${RUN_ID}" =~ ^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$ ]] || die "RUN_ID must be a DNS label (lowercase, digits, '-')"
RAMP="${RAMP:-60s}"; PEAK="${PEAK:-600}"; DURATION="${DURATION:-120s}"; RAMPDOWN="${RAMPDOWN:-30s}"
MAX_VUS="${MAX_VUS:-300}"; PERFORMANCES="${PERFORMANCES:-24}"; QUANTITY="${QUANTITY:-2}"
JOB="${TOKEN}-onsale-${RUN_ID}"
OUT="${TKT_ROOT}/.runs/${TOKEN}"; mkdir -p "${OUT}"
kubectl get ns "${NS}" >/dev/null 2>&1 || die "namespace ${NS} absent — run scripts/reset.sh ${TOKEN} first"

log "on-sale ${RUN_ID}: peak ${PEAK} orders/min per side, ramp ${RAMP}, hold ${DURATION}, rampdown ${RAMPDOWN}, max ${MAX_VUS} VUs"
kubectl -n "${NS}" create configmap "${TOKEN}-onsale-script" --from-file=onsale.js="${TKT_ROOT}/load/onsale.js" --dry-run=client -o yaml \
  | kubectl label --local -f - "${TOKEN_LABEL}=${TOKEN}" "${SIDE_LABEL}=after" app.kubernetes.io/name=onsale-load -o yaml \
  | kubectl apply -f - >/dev/null
TOKEN="${TOKEN}" NS_AFTER="${NS}" HOST_BEFORE="$(host_before "${TOKEN}")" HOST_AFTER="$(host_after "${TOKEN}")" ECR_PREFIX="${ECR_PREFIX}" \
RUN_ID="${RUN_ID}" RAMP="${RAMP}" PEAK="${PEAK}" DURATION="${DURATION}" RAMPDOWN="${RAMPDOWN}" MAX_VUS="${MAX_VUS}" \
PERFORMANCES="${PERFORMANCES}" QUANTITY="${QUANTITY}" \
  envsubst '${TOKEN} ${NS_AFTER} ${HOST_BEFORE} ${HOST_AFTER} ${ECR_PREFIX} ${RUN_ID} ${RAMP} ${PEAK} ${DURATION} ${RAMPDOWN} ${MAX_VUS} ${PERFORMANCES} ${QUANTITY}' \
  < "${TKT_ROOT}/load/onsale-job.yaml" | kubectl apply -f -

log "waiting for job/${JOB} to start"
for i in $(seq 1 60); do
  phase="$(kubectl -n "${NS}" get pods -l "job-name=${JOB}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)"
  case "${phase}" in Running|Succeeded|Failed) break ;; esac
  sleep 5
done
[ -n "${phase:-}" ] || die "k6 pod for ${JOB} never started"
kubectl -n "${NS}" logs -f "job/${JOB}" 2>&1 | tee "${OUT}/onsale-${RUN_ID}.log" | grep -v -E '^\s*$' || true
kubectl -n "${NS}" wait "job/${JOB}" --for=condition=complete --timeout=60s >/dev/null 2>&1 && status=complete || status=failed

sed -n '/=== ONSALE_SUMMARY_BEGIN ===/,/=== ONSALE_SUMMARY_END ===/p' "${OUT}/onsale-${RUN_ID}.log" | sed '1d;$d' > "${OUT}/onsale-${RUN_ID}.json"
jq -e .run_id "${OUT}/onsale-${RUN_ID}.json" >/dev/null 2>&1 || die "no summary in the k6 output (job ${status}); see ${OUT}/onsale-${RUN_ID}.log"
cp "${OUT}/onsale-${RUN_ID}.json" "${OUT}/onsale-latest.json"
kubectl -n "${NS}" create configmap "${TOKEN}-onsale-summary" --from-file=summary.json="${OUT}/onsale-${RUN_ID}.json" \
  --from-literal=run_id="${RUN_ID}" --from-literal=job="${JOB}" --dry-run=client -o yaml \
  | kubectl label --local -f - "${TOKEN_LABEL}=${TOKEN}" "${SIDE_LABEL}=after" app.kubernetes.io/name=onsale-load -o yaml \
  | kubectl apply -f - >/dev/null
log "summary: ${OUT#${REPO_ROOT}/}/onsale-${RUN_ID}.json and configmap ${NS}/${TOKEN}-onsale-summary (job ${status})"
jq -r '.sides | to_entries[] | "   \(.key): fired=\(.value.fired) accepted=\(.value.accepted) p95=\(.value.latency_ms.p95)ms statuses=\(.value.statuses|tostring)"' "${OUT}/onsale-${RUN_ID}.json"
[ "${status}" = complete ]
