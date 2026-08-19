#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# pain_portal.sh — Beat 1 "the estate fights back": total blast radius of the
# legacy single-process portal (services/legacy-portal), fully local.
#
# The portal bundles three bounded contexts (announcements, user preferences,
# feedback) into ONE JVM process. This harness starts that unmodified fat JAR
# under the memory ceiling of the VM it "runs on today" (opt-in, harness-only:
# -Xmx${PAIN_HEAP} -XX:+ExitOnOutOfMemoryError), then drives ONE capability —
# the feedback module — with legitimate, validation-passing API traffic until
# its unbounded findAll() query exhausts the shared heap. The JVM dies, and all
# three capabilities go down together. No portal code is modified and nothing
# here runs by default; the golden path (run-onprem.sh, compose, make test)
# is untouched.
#
# Usage (via make, from the repo root):
#   make tp-pain-aws           # build if needed, start, seed, show green strip
#   make tp-pain-aws-break     # kill ONE capability -> whole portal dies
#   make tp-pain-aws-restore   # clean restart, green strip again
#   make tp-pain-aws-stop      # stop and clean up
#
# Direct:
#   scripts/tp_portal/pain_portal.sh <start|status|watch|break|restore|stop|selftest>
#
# Tunables (env): PAIN_PORT=8095 PAIN_HEAP=64m PAIN_ROWS=20000 SKIP_BUILD=0
# ------------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="${REPO_ROOT}/services/legacy-portal"
JAR="${APP_DIR}/target/legacy-portal.jar"

PAIN_PORT="${PAIN_PORT:-8095}"
PAIN_HEAP="${PAIN_HEAP:-64m}"
PAIN_ROWS="${PAIN_ROWS:-20000}"
BASE="http://localhost:${PAIN_PORT}"
PID_FILE="${TMPDIR:-/tmp}/ow-tp-pain-portal.pid"
LOG_FILE="${TMPDIR:-/tmp}/ow-tp-pain-portal.log"

RED=$'\033[31m'; GREEN=$'\033[32m'; BOLD=$'\033[1m'; RESET=$'\033[0m'

usage() {
  sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

pid_alive() {
  [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null
}

probe() { # probe <url> -> 0 if HTTP 200
  [[ "$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$1" 2>/dev/null)" == "200" ]]
}

status_row() { # status_row <capability> <route> <url>
  local label
  if probe "$3"; then label="${GREEN}UP${RESET}"; else label="${RED}DOWN${RESET}"; fi
  printf '  %-18s %-38s %b\n' "$1" "$2" "${label}"
}

status_strip() {
  local proc
  if pid_alive; then proc="${GREEN}UP (pid $(cat "${PID_FILE}"))${RESET}"; else proc="${RED}DOWN${RESET}"; fi
  echo "${BOLD}legacy-portal — one process, three capabilities (${BASE})${RESET}"
  printf '  %-18s %-38s %b\n' "portal process" "java -jar legacy-portal.jar" "${proc}"
  status_row "announcements" "GET /api/announcements" "${BASE}/api/announcements"
  status_row "preferences" "GET /api/preferences/otter" "${BASE}/api/preferences/otter"
  status_row "feedback" "GET /api/feedback/average-rating" "${BASE}/api/feedback/average-rating"
}

all_up() {
  pid_alive \
    && probe "${BASE}/api/announcements" \
    && probe "${BASE}/api/preferences/otter" \
    && probe "${BASE}/api/feedback/average-rating"
}

seed() {
  curl -s -o /dev/null -X POST -H 'Content-Type: application/json' \
    -d '{"title":"Scheduled maintenance","body":"The portal will be unavailable Sunday 02:00-04:00 UTC.","published":true}' \
    "${BASE}/api/announcements"
  curl -s -o /dev/null -X PUT -H 'Content-Type: application/json' \
    -d '{"theme":"dark","locale":"en-GB","emailNotifications":true}' \
    "${BASE}/api/preferences/otter"
  curl -s -o /dev/null -X POST -H 'Content-Type: application/json' \
    -d '{"userId":"otter","rating":4,"message":"Portal works, mostly."}' \
    "${BASE}/api/feedback"
}

start() {
  if pid_alive; then
    echo "pain-portal: already running (pid $(cat "${PID_FILE}"))."
    status_strip
    return 0
  fi
  if [[ "${SKIP_BUILD:-0}" != "1" || ! -f "${JAR}" ]]; then
    echo "pain-portal: building legacy-portal fat JAR (unmodified golden source)..."
    (cd "${APP_DIR}" && if [[ -x ./mvnw ]]; then ./mvnw -B -q -DskipTests package; else mvn -B -q -DskipTests package; fi)
  fi
  echo "pain-portal: starting the portal under its VM memory ceiling (-Xmx${PAIN_HEAP}, exit on OOM)..."
  nohup java "-Xmx${PAIN_HEAP}" -XX:+ExitOnOutOfMemoryError -jar "${JAR}" \
    --server.port="${PAIN_PORT}" > "${LOG_FILE}" 2>&1 &
  echo $! > "${PID_FILE}"
  for _ in $(seq 1 60); do
    probe "${BASE}/health" && break
    sleep 1
  done
  if ! probe "${BASE}/health"; then
    echo "pain-portal: portal failed to become healthy; see ${LOG_FILE}" >&2
    terminate
    rm -f "${PID_FILE}"
    exit 1
  fi
  seed
  status_strip
}

flood_feedback() {
  local msg payload_file
  msg="$(printf 'x%.0s' $(seq 1 2000))"
  payload_file="$(mktemp)"
  printf '{"userId":"pain","rating":5,"message":"%s"}' "${msg}" > "${payload_file}"
  echo "pain-portal: ONE capability under load — POST /api/feedback x${PAIN_ROWS} (all valid requests)..."
  local batch=1000 posted=0
  while (( posted < PAIN_ROWS )) && pid_alive; do
    seq 1 "${batch}" | xargs -P 32 -I{} curl -s -o /dev/null -m 3 -X POST \
      -H 'Content-Type: application/json' --data "@${payload_file}" \
      "${BASE}/api/feedback" 2>/dev/null || true
    posted=$(( posted + batch ))
    printf '\r  feedback rows submitted: ~%d/%d' "${posted}" "${PAIN_ROWS}"
  done
  printf '\n'
  rm -f "${payload_file}"
}

break_portal() {
  if ! all_up; then
    echo "pain-portal: portal is not fully up — run 'make tp-pain-aws' first." >&2
    status_strip
    exit 1
  fi
  echo "${BOLD}=== BEFORE: every capability healthy ===${RESET}"
  status_strip
  echo
  flood_feedback
  echo "pain-portal: now a handful of ordinary feedback reads (findAll() loads every row into the shared heap)..."
  local volley
  for volley in $(seq 1 10); do
    pid_alive || break
    seq 1 8 | xargs -P 8 -I{} curl -s -o /dev/null -m 20 \
      "${BASE}/api/feedback?userId=pain" 2>/dev/null || true
    sleep 1
    pid_alive || break
  done
  for _ in $(seq 1 10); do
    pid_alive || break
    sleep 1
  done
  echo
  if pid_alive; then
    echo "pain-portal: portal unexpectedly survived — raise PAIN_ROWS or lower PAIN_HEAP and retry." >&2
    status_strip
    exit 1
  fi
  echo "${BOLD}=== AFTER: the feedback module OOM-killed the shared JVM ===${RESET}"
  tail -n 1 "${LOG_FILE}" | sed 's/^/  portal log: /'
  status_strip
  echo
  echo "  One capability failed. Three went down. That is the blast radius of a single process."
  echo "  Restore with: make tp-pain-aws-restore"
}

terminate() { # SIGTERM, escalate to SIGKILL if the JVM lingers
  kill "$(cat "${PID_FILE}")" 2>/dev/null || true
  local _i
  for _i in $(seq 1 10); do pid_alive || return 0; sleep 1; done
  kill -9 "$(cat "${PID_FILE}")" 2>/dev/null || true
  for _i in $(seq 1 5); do pid_alive || return 0; sleep 1; done
}

restore() {
  if pid_alive; then
    terminate
  fi
  rm -f "${PID_FILE}"
  SKIP_BUILD=1 start
}

stop() {
  if pid_alive; then
    terminate
    echo "pain-portal: stopped."
  else
    echo "pain-portal: not running."
  fi
  rm -f "${PID_FILE}"
}

watch_strip() {
  while true; do
    clear
    date -u '+%Y-%m-%dT%H:%M:%SZ'
    status_strip
    sleep 1
  done
}

selftest() {
  # Offline self-test for the smoke gate: nothing is started, no ports touched.
  bash -n "${BASH_SOURCE[0]}"
  command -v java > /dev/null || { echo "selftest: java not on PATH" >&2; exit 1; }
  command -v curl > /dev/null || { echo "selftest: curl not on PATH" >&2; exit 1; }
  command -v xargs > /dev/null || { echo "selftest: xargs not on PATH" >&2; exit 1; }
  [[ -d "${APP_DIR}" ]] || { echo "selftest: ${APP_DIR} missing" >&2; exit 1; }
  [[ -f "${APP_DIR}/pom.xml" ]] || { echo "selftest: legacy-portal pom.xml missing" >&2; exit 1; }
  grep -q 'ExitOnOutOfMemoryError' "${BASH_SOURCE[0]}"
  echo "pain-portal selftest: OK (script parses, tools present, portal source present)"
}

case "${1:-}" in
  start) start ;;
  status) status_strip ;;
  watch) watch_strip ;;
  break) break_portal ;;
  restore) restore ;;
  stop) stop ;;
  selftest) selftest ;;
  *) usage; exit 1 ;;
esac
