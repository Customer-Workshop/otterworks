#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Run feedback-service directly on a host (no containers, no Kubernetes).
#
# By default it uses the embedded H2 database so it runs self-contained; point it at a real
# PostgreSQL by exporting SPRING_PROFILES_ACTIVE=postgres and SPRING_DATASOURCE_*.
#
# Usage:
#   ./scripts/run-local.sh            # build (if needed) + run with embedded H2
#   SKIP_BUILD=1 ./scripts/run-local.sh
# ------------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
JAR="${APP_DIR}/target/feedback-service.jar"

cd "${APP_DIR}"

if [[ "${SKIP_BUILD:-0}" != "1" || ! -f "${JAR}" ]]; then
  echo "[run-local] Building feedback-service fat JAR..."
  if [[ -x ./mvnw ]]; then
    ./mvnw -B -DskipTests package
  else
    mvn -B -DskipTests package
  fi
fi

echo "[run-local] Starting feedback-service on port ${SERVER_PORT:-8096}..."
exec java -jar "${JAR}"
