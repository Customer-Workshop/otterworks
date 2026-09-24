#!/usr/bin/env bash
# plant-partial-run.sh <namespace-token> [--manifest <path>]
#
# MIG-06 "duplicate source key from a partially completed prior run" cannot live in Db2: ARCH_KEY
# is the primary key of ARCHIVE.DOCARCH, so the source holds each MIG06-* key exactly once. The
# duplicate is planted on the TARGET instead, by simulating an abandoned earlier run that already
# staged the five keys and left a stale mig.key_ranges row (SEED-SPEC.md §8). When the real run
# loads MIG06-0000000001..05, UX_stg_DOCARCH_source_key raises SQLSTATE 23000 -> DUPLICATE_SOURCE_KEY.
#
# Meant to be called by the migration job's pre-run hook / `make demo-up` for the *after* namespace
# only, after `ldm init` created the mig.*/stg.* schema. Idempotent (the fixture uses IF NOT EXISTS).
#
# Preferred path is the job's own applier (sets SESSION_CONTEXT ldm.namespace and records the file):
#   python -m ldm init --manifest <manifest> --namespace <NS> --apply-sql <this fixture>
# Fallback (no ldm on PATH) uses sqlcmd with AZSQL_SERVER / AZSQL_DATABASE / AZSQL_USER / AZSQL_PASSWORD.
set -euo pipefail

NS="${1:?usage: plant-partial-run.sh <namespace-token> [--manifest <path>]}"
shift || true
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
MANIFEST="$ROOT/migration/manifest.yaml"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
FIXTURE="$HERE/fixtures/mig06_prior_run.sql"
[[ -f "$FIXTURE" ]] || { echo "fixture missing: $FIXTURE" >&2; exit 12; }
[[ "$NS" =~ ^[a-z][a-z0-9]{1,11}-after$ ]] || { echo "refusing: MIG-06 fixture is only planted in an *-after namespace (got '$NS')" >&2; exit 2; }

if python3 -c 'import ldm' 2>/dev/null; then
  exec python3 -m ldm init --manifest "$MANIFEST" --namespace "$NS" --apply-sql "$FIXTURE"
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
