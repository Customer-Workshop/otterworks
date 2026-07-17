#!/usr/bin/env bash
# Deploy PgBouncer in otterworks-platform to bound total RDS connections at
# high-tens of tenants. See docs/scaling.md §3 and k8s/pgbouncer.yaml.
# Requires DB_PASSWORD in the environment (never passed on argv to the pods).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS=otterworks-platform
: "${DB_PASSWORD:?set DB_PASSWORD}"

RDS_HOST="${RDS_HOST:?set RDS_HOST}"
RDS_PORT="${RDS_PORT:-5432}"
DB_USER="${DB_USER:-otterworks_admin}"

kubectl create namespace "${NS}" --dry-run=client -o yaml | kubectl apply -f -
# stdin-applied secret so the password never appears on a process argv
kubectl -n "${NS}" create secret generic pgbouncer-auth \
  --from-literal=RDS_HOST="${RDS_HOST}" \
  --from-literal=RDS_PORT="${RDS_PORT}" \
  --from-literal=DB_USER="${DB_USER}" \
  --from-literal=DB_PASSWORD="${DB_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f "${HERE}/../k8s/pgbouncer.yaml"
kubectl -n "${NS}" rollout status deploy/pgbouncer --timeout=120s
echo "[pgbouncer] ready at pgbouncer.${NS}:6432"
