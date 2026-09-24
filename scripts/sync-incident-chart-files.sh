#!/usr/bin/env bash
# Keep the document-service chart's copies of the incident alert rules and
# dashboard identical to their sources. Helm's .Files.Get cannot read outside
# the chart directory, so the chart carries generated copies.
#
#   scripts/sync-incident-chart-files.sh          # copy sources into the chart
#   scripts/sync-incident-chart-files.sh --check  # fail if a copy has drifted
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHART_FILES="${REPO_ROOT}/infrastructure/helm/document-service/files"
PAIRS=(
  "observability/prometheus/incident_alerts.yml:incident_alerts.yml"
  "observability/grafana/dashboards/incident-responder.json:incident-responder.json"
)

check=false
[ "${1:-}" = "--check" ] && check=true

rc=0
for pair in "${PAIRS[@]}"; do
  src="${REPO_ROOT}/${pair%%:*}"
  dst="${CHART_FILES}/${pair##*:}"
  if "${check}"; then
    if ! cmp -s "${src}" "${dst}"; then
      echo "drift: ${dst#"${REPO_ROOT}"/} differs from ${pair%%:*} (run scripts/sync-incident-chart-files.sh)" >&2
      rc=1
    fi
  else
    mkdir -p "${CHART_FILES}"
    cp "${src}" "${dst}"
    echo "synced ${pair%%:*} -> ${dst#"${REPO_ROOT}"/}"
  fi
done
exit "${rc}"
