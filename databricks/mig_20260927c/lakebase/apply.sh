#!/usr/bin/env bash
# Apply the wave-1 Lakebase DDL to ow_tp (project ow-tp-billing, branch mig-20260927c-w0) as the
# migration service principal, in dependency order: 10_billing_state.sql creates the eight
# unit-owned state tables, then 11_pkg_ow_util.sql, 12_pkg_plans.sql, 13_pkg_rating.sql and
# 14_pkg_invoicing.sql install the converted package routines. A rerun lands the declared shape
# and must be followed by extract_state.py | load_state.py.
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
  -f 10_billing_state.sql \
  -f 11_pkg_ow_util.sql \
  -f 12_pkg_plans.sql \
  -f 13_pkg_rating.sql \
  -f 14_pkg_invoicing.sql
