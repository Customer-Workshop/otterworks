#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# OtterWorks legacy-data-migration demo — expired-namespace reaper (ops unit).
#
#   scripts/demo-reaper.sh [--dry-run|--apply] [--grace 15m]
#
# Finds every resource tagged demo=legacy-data-migration whose `expires` tag
# (absolute UTC, §3.3) is in the past - in AWS (Resource Groups Tagging API),
# Azure (`az resource list --tag`) and Kubernetes (namespace annotation
# demo/expires) - groups them by their `namespace` tag and runs
# scripts/demo-destroy.sh for each. Default is --dry-run: report only.
# Runs hourly from .github/workflows/demo-reaper.yml with --apply.
#
# A namespace tag that does not match the token regex is reported and skipped:
# the reaper never passes an unvalidated string to demo-destroy.
# ------------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/demo-common.sh
source "${SCRIPT_DIR}/lib/demo-common.sh"

APPLY=0; GRACE="${REAPER_GRACE:-15m}"
while [ $# -gt 0 ]; do
  case "$1" in
    --apply)   APPLY=1; shift ;;
    --dry-run) APPLY=0; shift ;;
    --grace)   GRACE="$2"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" 2 ;;
  esac
done
[ "${APPLY}" = "1" ] || DRY_RUN=1
export DRY_RUN
require_bins aws kubectl jq

NOW_EPOCH="$(date +%s)"
GRACE_SECS="$(( $(iso_to_epoch "$(ttl_to_expires "${GRACE}")") - NOW_EPOCH ))"
CUTOFF=$((NOW_EPOCH - GRACE_SECS))
dlog "reaper $( [ "${APPLY}" = "1" ] && echo APPLY || echo DRY-RUN ) at $(now_utc); expired = expires + ${GRACE} < now"

# token<TAB>expires<TAB>source, one per resource
CANDIDATES="$(mktemp)"; trap 'rm -f "${CANDIDATES}"' EXIT

# --- AWS ------------------------------------------------------------------------------
if aws sts get-caller-identity >/dev/null 2>&1; then
  aws resourcegroupstaggingapi get-resources --region "${AWS_REGION}" \
    --tag-filters "Key=demo,Values=${DEMO_NAME}" --output json 2>/dev/null \
    | jq -r '.ResourceTagMappingList[] | (.Tags|from_entries) as $t | select($t.namespace and $t.expires) | "\($t.namespace)\t\($t.expires)\taws:\(.ResourceARN)"' \
    | while IFS=$'\t' read -r cns cexp carn; do
        # drop stale tagging-index entries for already-deleted resources
        if aws_arn_exists "${carn#aws:}"; then printf '%s\t%s\t%s\n' "${cns}" "${cexp}" "${carn}"; fi
      done >> "${CANDIDATES}" || dwarn "AWS tagging API query failed"
else
  dwarn "no AWS credentials; skipping AWS discovery"
fi

# --- Azure ----------------------------------------------------------------------------
if az_available && command -v az >/dev/null 2>&1; then
  if DRY_RUN=0 az_login 2>/dev/null; then
    az resource list --tag "demo=${DEMO_NAME}" -o json 2>/dev/null \
      | jq -r '.[] | select(.tags.namespace and .tags.expires) | "\(.tags.namespace)\t\(.tags.expires)\tazure:\(.id)"' >> "${CANDIDATES}" || dwarn "az resource list failed"
    az group list --tag "demo=${DEMO_NAME}" -o json 2>/dev/null \
      | jq -r '.[] | select(.tags.namespace and .tags.expires) | "\(.tags.namespace)\t\(.tags.expires)\tazure:\(.id)"' >> "${CANDIDATES}" || true
  else
    dwarn "az login failed; skipping Azure discovery"
  fi
else
  dwarn "AZURE_* not set or az missing; skipping Azure discovery"
fi

# --- Kubernetes -------------------------------------------------------------------------
if DRY_RUN=0 ensure_kubeconfig 2>/dev/null && kubectl get ns >/dev/null 2>&1; then
  kubectl get ns -l "demo/name=${DEMO_NAME}" -o json 2>/dev/null \
    | jq -r '.items[] | select(.metadata.labels["demo/namespace"]) |
        (.metadata.annotations["demo/expires"] // .metadata.annotations["demo/expires-at"] // "") as $e |
        select($e != "") | "\(.metadata.labels["demo/namespace"])\t\($e)\tk8s:namespace/\(.metadata.name)"' >> "${CANDIDATES}" || dwarn "kubectl namespace query failed"
else
  dwarn "no cluster access; skipping Kubernetes discovery"
fi

# --- group + decide ---------------------------------------------------------------------------
TOTAL="$(wc -l < "${CANDIDATES}" | tr -d ' ')"
dlog "${TOTAL} tagged resource(s) found"
declare -A EXPIRED=() LIVE=() BAD=()
while IFS=$'\t' read -r token expires src; do
  [ -n "${token}" ] || continue
  if ! [[ "${token}" =~ ${TOKEN_REGEX} ]] || [ "${token%-*}" = "main" ]; then BAD["${token}"]+="${src} "; continue; fi
  epoch="$(iso_to_epoch "${expires}")"
  if [ "${epoch}" -eq 0 ]; then BAD["${token}"]+="${src}(bad expires '${expires}') "; continue; fi
  if [ "${epoch}" -lt "${CUTOFF}" ]; then EXPIRED["${token}"]+="${src} "; else LIVE["${token}"]="${expires}"; fi
done < "${CANDIDATES}"

for t in "${!LIVE[@]}"; do dlog "live    ${t} (expires ${LIVE[$t]})"; done
for t in "${!BAD[@]}"; do dwarn "skipped ${t}: namespace tag does not match ${TOKEN_REGEX} or has an unreadable expires tag - review manually: ${BAD[$t]}"; done
[ "${#EXPIRED[@]}" -gt 0 ] || { dlog "nothing expired"; exit 0; }

rc=0
for t in $(printf '%s\n' "${!EXPIRED[@]}" | sort); do
  # A namespace that is still live under another resource's tag is not touched:
  # every resource of a token shares one expires value, so a mismatch means a
  # redeploy with a longer TTL is in flight.
  if [ -n "${LIVE[$t]:-}" ]; then dwarn "${t}: some resources expired but others live until ${LIVE[$t]}; skipping"; continue; fi
  dlog "expired ${t}: ${EXPIRED[$t]}"
  if [ "${APPLY}" = "1" ]; then
    "${SCRIPT_DIR}/demo-destroy.sh" "${t}" || { derr "destroy of ${t} failed"; rc=1; }
  else
    dlog "[dry-run] would run: scripts/demo-destroy.sh ${t}"
  fi
done
exit "${rc}"
