#!/usr/bin/env bash
# Apply 00_scaffold.sql to Lakebase ow_tp (project ow-tp-billing, branch mig-20260927c-w0) as the
# migration service principal. Idempotent: the DDL drops and recreates the four unit-owned tables
# (and the schema when empty), so a rerun lands the declared shape and must be followed by
# extract_reference.py | load_reference.py.
# Password comes from ~/.pgpass (token minted by `databricks postgres generate-database-credential`);
# nothing here prints or stores a credential.
set -euo pipefail
cd "$(dirname "$0")"
PGSSLMODE=require psql \
  -h ep-crimson-wave-d1jr0yo9.database.us-west-2.cloud.databricks.com \
  -p 5432 \
  -U d9d1c4ec-29da-4ec7-9aa0-e932710d61e2 \
  -d ow_tp \
  -v ON_ERROR_STOP=1 \
  -f 00_scaffold.sql
