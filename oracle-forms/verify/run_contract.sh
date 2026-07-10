#!/usr/bin/env bash
# Boot the billing service (H2, in-memory), run the contract-parity harness
# against it, then tear it down. Self-contained: no Docker or external DB.
#
# Usage: oracle-forms/verify/run_contract.sh
# Env:   BASE_URL (default http://localhost:8092), PORT (default 8092)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORMS_DIR="$(cd "$HERE/.." && pwd)"
APP_DIR="$FORMS_DIR/spring-boot-app"
PORT="${PORT:-8092}"
export BASE_URL="${BASE_URL:-http://localhost:$PORT}"

# --- locate a Java 21 runtime ------------------------------------------------
find_java() {
  if [[ -n "${JAVA_HOME:-}" && -x "$JAVA_HOME/bin/java" ]]; then
    echo "$JAVA_HOME/bin/java"; return
  fi
  local candidate
  candidate="$(ls -d "$HOME"/.sdkman/candidates/java/21* 2>/dev/null | head -1 || true)"
  if [[ -n "$candidate" && -x "$candidate/bin/java" ]]; then
    echo "$candidate/bin/java"; return
  fi
  echo java
}
JAVA_BIN="$(find_java)"

# --- build the jar if needed -------------------------------------------------
JAR="$APP_DIR/build/libs/billing-service.jar"
if [[ ! -f "$JAR" ]]; then
  echo ">> building billing-service.jar"
  # Only export JAVA_HOME when JAVA_BIN is an absolute path we resolved; a bare
  # "java" on PATH must not become JAVA_HOME="." (which breaks the Gradle wrapper).
  if [[ "$JAVA_BIN" == /* ]]; then
    ( cd "$APP_DIR" && JAVA_HOME="$(dirname "$(dirname "$JAVA_BIN")")" ./gradlew bootJar -q --console=plain )
  else
    ( cd "$APP_DIR" && ./gradlew bootJar -q --console=plain )
  fi
fi

# --- start the service --------------------------------------------------------
echo ">> starting billing-service on port $PORT"
"$JAVA_BIN" -jar "$JAR" --server.port="$PORT" > /tmp/billing-verify.log 2>&1 &
APP_PID=$!
cleanup() { kill "$APP_PID" 2>/dev/null || true; }
trap cleanup EXIT

# --- run the harness ----------------------------------------------------------
python3 -m pytest "$HERE" -v
