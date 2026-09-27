#!/usr/bin/env bash
# Apply 00_scaffold.sql to Lakebase ow_tp (project ow-tp-billing, branch mig-20260927-w0) as the
# migration service principal. Idempotent: the DDL is IF NOT EXISTS throughout, so a rerun is a no-op.
# Password comes from ~/.pgpass (token minted by `databricks postgres generate-database-credential`);
# nothing here prints or stores a credential.
set -euo pipefail
cd "$(dirname "$0")"
PGSSLMODE=require psql \
  -h ep-wild-hat-d120fhwn.database.us-west-2.cloud.databricks.com \
  -p 5432 \
  -U d9d1c4ec-29da-4ec7-9aa0-e932710d61e2 \
  -d ow_tp \
  -v ON_ERROR_STOP=1 \
  -f 00_scaffold.sql
