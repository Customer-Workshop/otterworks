#!/usr/bin/env bash
# Apply 00_scaffold.sql to Lakebase ow_tp (project ow-tp-billing, branch mig-20260927c-w0).
# Idempotent: the DDL is IF NOT EXISTS only, so a rerun changes nothing.
# Usage: ./apply.sh [-h host] [-U user] [-d db]
# The only connection the migration guard allows is the declared target below, so -h/-U/-d
# exist for explicitness and are verified against it rather than substituted into argv.
# Password comes from ~/.pgpass (token minted by `databricks postgres generate-database-credential`);
# nothing here prints or stores a credential.
set -euo pipefail

host=ep-crimson-wave-d1jr0yo9.database.us-west-2.cloud.databricks.com
user=d9d1c4ec-29da-4ec7-9aa0-e932710d61e2
db=ow_tp

while getopts "h:U:d:" opt; do
  case "$opt" in
    h) host="$OPTARG" ;;
    U) user="$OPTARG" ;;
    d) db="$OPTARG" ;;
    *) echo "usage: $0 [-h host] [-U user] [-d db]" >&2; exit 64 ;;
  esac
done

if [ "$host" != "ep-crimson-wave-d1jr0yo9.database.us-west-2.cloud.databricks.com" ] ||
   [ "$user" != "d9d1c4ec-29da-4ec7-9aa0-e932710d61e2" ]; then
  echo "refusing: only the declared Lakebase target principal/endpoint is permitted" >&2
  exit 2
fi

actual_db=$(PGSSLMODE=require psql \
  -h ep-crimson-wave-d1jr0yo9.database.us-west-2.cloud.databricks.com \
  -U d9d1c4ec-29da-4ec7-9aa0-e932710d61e2 \
  -d "$db" -tAc "select current_database()")
if [ "$actual_db" != "ow_tp" ]; then
  echo "refusing to apply: connected to database '$actual_db', expected 'ow_tp'" >&2
  exit 2
fi

cd "$(dirname "$0")"
PGSSLMODE=require psql \
  -h ep-crimson-wave-d1jr0yo9.database.us-west-2.cloud.databricks.com \
  -U d9d1c4ec-29da-4ec7-9aa0-e932710d61e2 \
  -d ow_tp \
  -v ON_ERROR_STOP=1 \
  -f 00_scaffold.sql
