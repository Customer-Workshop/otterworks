#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PSQL_BIN="${PSQL_BIN:-psql}"
KUBECTL_BIN="${KUBECTL_BIN:-kubectl}"
DSN="${DW_POSTGRES_DSN:-host=127.0.0.1 port=15432 dbname=analytics_dw user=dw_admin password=dw_local_dev sslmode=disable}"
NAMESPACE="${DW_NAMESPACE:-legacy-dw}"
POD="${DW_POD:-analytics-dw-0}"
WORK_DIR="${TMPDIR:-/tmp}/dw-estate-bootstrap.$$"

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

reset_estate() {
    "$PSQL_BIN" "$DSN" -v ON_ERROR_STOP=1 -q <<'SQL'
DROP SCHEMA IF EXISTS mart CASCADE;
DROP SCHEMA IF EXISTS core CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA staging;
CREATE SCHEMA core;
CREATE SCHEMA mart;
SQL
    printf '%s\n' "legacy estate reset"
}

if [[ "${1:-}" == "--reset" ]]; then
    reset_estate
    exit 0
fi
if [[ "${1:-}" != "" ]]; then
    printf 'usage: %s [--reset]\n' "$0" >&2
    exit 2
fi

mkdir -p "$WORK_DIR/ddl" "$WORK_DIR/procs"
"$KUBECTL_BIN" wait --for=condition=Ready "pod/$POD" \
    -n "$NAMESPACE" --timeout="${DW_READY_TIMEOUT:-180s}" >/dev/null
"$PSQL_BIN" "$DSN" -v ON_ERROR_STOP=1 -q -c \
    "CREATE SCHEMA IF NOT EXISTS staging; CREATE SCHEMA IF NOT EXISTS core; CREATE SCHEMA IF NOT EXISTS mart;"

"$PYTHON_BIN" "$ROOT/dw/legacy-estate/ddl/compat/redshift_to_postgres.py" \
    --check "$ROOT/dw/legacy-estate/ddl/staging" \
    "$ROOT/dw/legacy-estate/ddl/core" \
    "$ROOT/dw/legacy-estate/ddl/mart" >/dev/null
"$PYTHON_BIN" "$ROOT/dw/legacy-estate/ddl/compat/redshift_to_postgres.py" \
    --out-dir "$WORK_DIR/ddl" \
    "$ROOT/dw/legacy-estate/ddl/staging" \
    "$ROOT/dw/legacy-estate/ddl/core" \
    "$ROOT/dw/legacy-estate/ddl/mart" >/dev/null
"$PSQL_BIN" "$DSN" -v ON_ERROR_STOP=1 -q \
    -f "$ROOT/dw/legacy-estate/ddl/compat/shims.sql"
for ddl in "$WORK_DIR"/ddl/*.sql; do
    "$PSQL_BIN" "$DSN" -v ON_ERROR_STOP=1 -q -f "$ddl"
done

"$PYTHON_BIN" "$ROOT/dw/legacy-estate/ddl/compat/redshift_to_postgres.py" \
    --out-dir "$WORK_DIR/procs" "$ROOT/dw/legacy-estate/procs" >/dev/null
for proc in "$WORK_DIR"/procs/*.sql; do
    "$PSQL_BIN" "$DSN" -v ON_ERROR_STOP=1 -q -f "$proc"
done
"$PSQL_BIN" "$DSN" -v ON_ERROR_STOP=1 -q \
    -f "$ROOT/dw/legacy-estate/seed/seed.sql"
"$PYTHON_BIN" "$ROOT/dw/legacy-estate/python/run_dag.py" \
    --dag legacy_dw_nightly --dsn "$DSN"
printf '%s\n' "legacy estate bootstrapped"
