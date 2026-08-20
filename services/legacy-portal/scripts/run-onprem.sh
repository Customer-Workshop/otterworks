#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Run legacy-portal directly on a VM / on-prem host (no containers, no Kubernetes).
#
# This mirrors how the component is deployed today: a plain Spring Boot fat JAR run
# on a host, typically under systemd (see ../deploy/legacy-portal.service). The app is the
# post-decomposition shell — it needs no database at all.
#
# Usage:
#   ./scripts/run-onprem.sh            # build (if needed) + run
#   SKIP_BUILD=1 ./scripts/run-onprem.sh
# ------------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
JAR="${APP_DIR}/target/legacy-portal.jar"

cd "${APP_DIR}"

if [[ "${SKIP_BUILD:-0}" != "1" || ! -f "${JAR}" ]]; then
  echo "[run-onprem] Building legacy-portal fat JAR..."
  if [[ -x ./mvnw ]]; then
    ./mvnw -B -DskipTests package
  else
    mvn -B -DskipTests package
  fi
fi

echo "[run-onprem] Starting legacy-portal on port ${SERVER_PORT:-8095}..."
exec java -jar "${JAR}"
