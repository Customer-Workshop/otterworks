#!/usr/bin/env bash
# plant-partial-run.sh <namespace-token> [--manifest <path>] [--provider postgresql|azuresql]
#
# MIG-06 "duplicate source key from a partially completed prior run" cannot live in Db2: ARCH_KEY
# is the primary key of ARCHIVE.DOCARCH, so the source holds each MIG06-* key exactly once. The
# duplicate is planted on the TARGET instead, by simulating an abandoned earlier run that already
# staged the five keys and left a stale mig.key_ranges row (SEED-SPEC.md §8). When the real run
# loads MIG06-0000000001..05, the (namespace, source_key) unique index raises SQLSTATE 23505 (PostgreSQL)
# / 23000 (Azure SQL) -> DUPLICATE_SOURCE_KEY. One fixture rendering per target provider.
#
# Meant to be called by the migration job's pre-run hook / `make demo-up` for the *after* namespace
# only, after `ldm init` created the mig.*/stg.* schema. Idempotent (the fixture uses IF NOT EXISTS).
#
# Preferred path is the job's own applier (sets the ldm.namespace session variable and records the file):
#   python -m ldm init --manifest <manifest> --namespace <NS> --apply-sql <this fixture>
# Fallback (no ldm on PATH): psql with PG_HOST / PG_PORT / PG_DATABASE / PG_USER / PG_PASSWORD, or
# sqlcmd with AZSQL_SERVER / AZSQL_DATABASE / AZSQL_USER / AZSQL_PASSWORD for --provider azuresql.
set -euo pipefail

NS="${1:?usage: plant-partial-run.sh <namespace-token> [--manifest <path>]}"
shift || true
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
MANIFEST="$ROOT/migration/manifest.yaml"
PROVIDER="postgresql"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$PROVIDER" in
  postgresql) FIXTURE="$HERE/fixtures/mig06_prior_run.postgresql.sql" ;;
  azuresql)   FIXTURE="$HERE/fixtures/mig06_prior_run.sql" ;;
  *) echo "unknown --provider '$PROVIDER' (postgresql|azuresql)" >&2; exit 2 ;;
esac
[[ -f "$FIXTURE" ]] || { echo "fixture missing: $FIXTURE" >&2; exit 12; }
[[ "$NS" =~ ^[a-z][a-z0-9]{1,11}-after$ ]] || { echo "refusing: MIG-06 fixture is only planted in an *-after namespace (got '$NS')" >&2; exit 2; }

if python3 -c 'import ldm' 2>/dev/null; then
  exec python3 -m ldm init --manifest "$MANIFEST" --namespace "$NS" --apply-sql "$FIXTURE"
fi

if [[ "$PROVIDER" == "postgresql" ]]; then
  : "${PG_HOST:?PG_HOST required when ldm is not installed}"
  : "${PG_DATABASE:?PG_DATABASE required when ldm is not installed}"
  : "${PG_USER:?PG_USER required}"
  : "${PG_PASSWORD:?PG_PASSWORD required}"
  command -v psql >/dev/null || { echo "neither python module ldm nor psql is available" >&2; exit 12; }
  # set_config(..., true) is transaction-local, so the fixture runs in the same transaction (-1).
  { printf "SELECT set_config('ldm.namespace', '%s', true);\n" "$NS"; cat "$FIXTURE"; } |
    PGPASSWORD="$PG_PASSWORD" psql -v ON_ERROR_STOP=1 -1 -q -h "$PG_HOST" -p "${PG_PORT:-5432}" -d "$PG_DATABASE" -U "$PG_USER" -f -
  echo "MIG-06 prior-run fixture applied to $PG_DATABASE for namespace $NS"
  exit 0
fi

: "${AZSQL_SERVER:?AZSQL_SERVER required when ldm is not installed}"
: "${AZSQL_DATABASE:?AZSQL_DATABASE required when ldm is not installed}"
: "${AZSQL_USER:?AZSQL_USER required}"
: "${AZSQL_PASSWORD:?AZSQL_PASSWORD required}"
command -v sqlcmd >/dev/null || { echo "neither python module ldm nor sqlcmd is available" >&2; exit 12; }

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
{
  printf "EXEC sp_set_session_context N'ldm.namespace', N'%s';\n" "$NS"
  cat "$FIXTURE"
} > "$TMP"
# Password is passed via SQLCMDPASSWORD (never on the command line / in ps output).
SQLCMDPASSWORD="$AZSQL_PASSWORD" sqlcmd -S "tcp:$AZSQL_SERVER,1433" -d "$AZSQL_DATABASE" -U "$AZSQL_USER" \
  -N -C -b -i "$TMP"
echo "MIG-06 prior-run fixture applied to $AZSQL_DATABASE for namespace $NS"
