#!/usr/bin/env bash
# incident/tenant.sh — arm the n-plus-one page on a tenant of the shared
# otterworks-dev cluster, or read its state, from a laptop with kubectl access.
#
#   incident/tenant.sh arm    <tenant-id> [duration-seconds]   seed the fixture, then run the list load
#   incident/tenant.sh status <tenant-id>                       queries/request + latency of one list call
#   incident/tenant.sh disarm <tenant-id>                       stop a load started by `arm`
#
# <tenant-id> is the tenant, not the branch: `main` for t-main.otterworks.app
# (branch main), `incident` for t-incident.demo.otterworks.app (branch
# demo-incident). The fixture is seeded through a port-forward to the tenant's
# document-service and the load goes through the shared ingress, so the alert
# measures what a user sees. Only n-plus-one is armable this way: it needs no
# chaos flag, just the fixture and the load, so it never changes the tenant's
# code, config or flags — see AGENTS.md for why that is the only thing allowed
# on t-main.
#
# Env: INCIDENT_LOAD_SCALE (default 0.25; a tenant runs one 500m worker),
#      INCIDENT_PORT (default 18083; must be free — the local Compose stack owns
#      8083), AWS/kubectl context for otterworks-dev.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/.." && pwd)"
STATE="${HERE}/.state"
PORT="${INCIDENT_PORT:-18083}"
export INCIDENT_LOAD_SCALE="${INCIDENT_LOAD_SCALE:-0.25}"

log() { printf '[tenant] %s\n' "$*" >&2; }
die() { log "$*"; exit 1; }

op="${1:-}"; tenant="${2:-}"
if [ -z "${op}" ] || [ -z "${tenant}" ]; then sed -n '2,20p' "$0"; exit 2; fi
case "${tenant}" in
  main) api_host="api-t-main.otterworks.app" ;;
  *)    api_host="api-t-${tenant}.demo.otterworks.app" ;;
esac
ns="otterworks-${tenant}"
pidfile="${STATE}/tenant-${tenant}.pid"
mkdir -p "${STATE}"

jwt_secret() {
  kubectl -n "${ns}" get secret document-service-secrets -o jsonpath='{.data.JWT_SECRET}' | base64 -d
}

# Seeding must reach the tenant's own document-service, so the forward has to
# own the local port: a listener already there (the Compose stack, another
# forward) would silently take the fixture instead.
with_port_forward() {
  if curl -s -o /dev/null "http://localhost:${PORT}/health" 2>/dev/null; then
    die "localhost:${PORT} is already serving something; set INCIDENT_PORT to a free port"
  fi
  kubectl -n "${ns}" port-forward "svc/document-service" "${PORT}:8083" >/dev/null 2>&1 &
  local pf=$!
  # shellcheck disable=SC2064  # expand the pid now; the local is gone by EXIT
  trap "kill ${pf} 2>/dev/null || true" RETURN EXIT
  for _ in $(seq 1 50); do
    kill -0 "${pf}" 2>/dev/null || die "port-forward to ${ns}/svc/document-service exited"
    curl -fsS -o /dev/null "http://localhost:${PORT}/health" 2>/dev/null && break
    sleep 0.2
  done
  curl -fsS -o /dev/null "http://localhost:${PORT}/health" 2>/dev/null ||
    die "port-forward to ${ns}/svc/document-service never became healthy"
  "$@"
}

seed() {
  INCIDENT_BASE_URL="http://localhost:${PORT}" make -C "${REPO}" incident-seed
}

case "${op}" in
  arm)
    duration="${3:-900}"
    [ -f "${pidfile}" ] && kill -0 "$(cat "${pidfile}")" 2>/dev/null && die "load already running for ${tenant} (pid $(cat "${pidfile}")); disarm first"
    JWT_SECRET="$(jwt_secret)"; export JWT_SECRET
    log "arming n-plus-one on ${ns} (${api_host}), load ${duration}s at scale ${INCIDENT_LOAD_SCALE}"
    with_port_forward seed
    INCIDENT_BASE_URL="https://${api_host}" \
      setsid make -C "${REPO}" incident-load SCENARIO=n-plus-one DURATION="${duration}" \
      >"${STATE}/tenant-${tenant}-load.log" 2>&1 &
    echo $! >"${pidfile}"
    log "load pid $(cat "${pidfile}") (log ${STATE}/tenant-${tenant}-load.log); DocumentListLatencyHigh fires in ~90s"
    log "watch: https://alertmanager.otterworks.app/#/alerts?filter=%7Bnamespace%3D%22${ns}%22%7D"
    ;;
  disarm)
    if [ -f "${pidfile}" ]; then
      pid="$(cat "${pidfile}")"
      kill -- -"${pid}" 2>/dev/null || kill "${pid}" 2>/dev/null || true
      rm -f "${pidfile}"
      log "load stopped for ${tenant}; alerts resolve within ~5m of the last slow request"
    else
      log "no load running for ${tenant}"
    fi
    ;;
  status)
    JWT_SECRET="$(jwt_secret)"; export JWT_SECRET
    owner="$(python3 -c "import yaml;print(yaml.safe_load(open('${HERE}/scenarios.yaml'))['seed']['owner_id'])")"
    token="$(uv run --quiet --with pyjwt==2.9.0 python -c "import jwt,os,time;o='${owner}';print(jwt.encode({'user_id':o,'sub':o,'exp':int(time.time())+600},os.environ['JWT_SECRET'],algorithm='HS256'))")"
    curl -s -D - -o /dev/null -H "Authorization: Bearer ${token}" \
      "https://${api_host}/api/v1/documents/?owner_id=${owner}&page=1&size=100" \
      | grep -i -E '^HTTP/|^x-db-queries|^x-request-duration-ms'
    ;;
  *) die "unknown op ${op}" ;;
esac
