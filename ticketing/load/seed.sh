#!/usr/bin/env bash
# Deterministic re-seed of BOTH sides from the same synthetic seed (ticketing/monolith/db/seed.sql and the
# services' Flyway copies of it), without re-deploying anything:
#   before: reset.sql + schema.sql + seed.sql through psql in the <token>-db pod, then a monolith restart
#           (drops its pooled connections / cached plans);
#   after:  drop and re-create the public schema of every service database, bounce any running service pod
#           and warm each service so Flyway rebuilds schema + reference data on boot.
# Ends by comparing seat availability of a few performances on the two public hosts.
#   usage: load/seed.sh <token>          (called by scripts/reset.sh after both deploys)
source "$(dirname "$0")/../scripts/lib.sh"
TOKEN="${1:-}"; validate_token "${TOKEN}"
ensure_kubeconfig
NSB="$(ns_before "${TOKEN}")"; NSA="$(ns_after "${TOKEN}")"
HB="https://$(host_before "${TOKEN}")"; HA="https://$(host_after "${TOKEN}")"
SECONDS=0
psql_in() { # psql_in <ns> <deployment> <user> <db>  (SQL on stdin)
  kubectl -n "$1" exec -i "deploy/$2" -- psql -q -v ON_ERROR_STOP=1 -U "$3" -d "$4"
}

log "seed: before (${NSB}) from monolith/db/{reset,schema,seed}.sql"
kubectl get ns "${NSB}" >/dev/null 2>&1 || die "namespace ${NSB} absent — run scripts/deploy-before.sh ${TOKEN} first"
cat "${TKT_ROOT}/monolith/db/reset.sql" "${TKT_ROOT}/monolith/db/schema.sql" "${TKT_ROOT}/monolith/db/seed.sql" \
  | psql_in "${NSB}" "${TOKEN}-db" boxoffice boxoffice >/dev/null
kubectl -n "${NSB}" rollout restart "deploy/${TOKEN}-monolith" >/dev/null
kubectl -n "${NSB}" rollout status  "deploy/${TOKEN}-monolith" --timeout=10m >/dev/null

if kubectl get ns "${NSA}" >/dev/null 2>&1; then
  log "seed: after (${NSA}) — reset service schemas, Flyway re-seeds on boot"
  for svc in orders seats payments confirmations; do
    printf 'DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO %s;\n' "${svc}" \
      | psql_in "${NSA}" "${TOKEN}-${svc}-db" "${svc}" "${svc}" >/dev/null
  done
  # anything currently running holds a pool onto the old schema: bounce it (0 pods at rest -> no-op)
  for sel in "serving.knative.dev/service=${TOKEN}-orders" "serving.knative.dev/service=${TOKEN}-seats" \
             "serving.knative.dev/service=${TOKEN}-confirmations" "app=${TOKEN}-payments" "app.kubernetes.io/name=orders-outbox-relay"; do
    kubectl -n "${NSA}" delete pod -l "${sel}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
  done
  # warm the request-driven services: the first request boots a revision, which runs Flyway V1+V2
  wait_http "${HA}/api/stats" 200 300
  wait_http "${HA}/api/performances/1/availability" 200 300
  wait_http "${HA}/api/confirmations/none" 404 300
else
  log "seed: after side absent (${NSA}) — before only"
fi

wait_http "${HB}/api/stats" 200 300
log "seed check: seat availability before | after"
mismatch=0
for perf in 1 7 13 24; do
  b="$(pub_curl "${HB}/api/performances/${perf}/availability" -s -m 20 | jq -c '{available,held,sold}')"
  a="$(kubectl get ns "${NSA}" >/dev/null 2>&1 && pub_curl "${HA}/api/performances/${perf}/availability" -s -m 20 | jq -c '{available,held,sold}' || echo n/a)"
  printf '   performance %-2s  %s | %s\n' "${perf}" "${b}" "${a}"
  [ "${a}" != n/a ] && [ "${a}" != "${b}" ] && mismatch=1
done
[ "${mismatch}" = 1 ] && die "seed mismatch between the two sides"
log "seed complete in ${SECONDS}s (before stats: $(pub_curl "${HB}/api/stats" -s -m 20 | jq -c . | cut -c1-160))"
