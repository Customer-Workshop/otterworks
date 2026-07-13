#!/usr/bin/env bash
#
# Run the nightly usage-rollup batch job (analytics-service) locally.
#
# This is the LEGACY "before" batch process for the batch -> event-driven
# re-architect demo: it bulk-loads analytics events and aggregates them into
# per-day usage rollups in a single synchronous pass. See
# docs/BATCH-USAGE-ROLLUP.md for the event-driven target.
#
# Usage:
#   scripts/run-usage-rollup.sh [output_path]
#
# Environment overrides:
#   ROLLUP_INPUT   Path (or classpath resource) of NDJSON events.
#                  Default: bundled seed /seed/usage-events.ndjson
#   ROLLUP_OUTPUT  Output JSON path. Default: rollup-output.json
#                  (overridden by the optional [output_path] argument)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${SCRIPT_DIR}/../services/analytics-service"

if [[ $# -ge 1 ]]; then
  export ROLLUP_OUTPUT="$1"
fi

echo "Running usage-rollup batch job (input=${ROLLUP_INPUT:-/seed/usage-events.ndjson}, output=${ROLLUP_OUTPUT:-rollup-output.json})"
cd "${SERVICE_DIR}"
exec sbt "runMain com.otterworks.analytics.batch.UsageRollupJob"
