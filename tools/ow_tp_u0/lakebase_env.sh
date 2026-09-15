#!/usr/bin/env bash
set -euo pipefail

: "${LAKEBASE_MIGRATION_HOST:?set the Lakebase primary endpoint host}"
: "${LAKEBASE_MIGRATION_USER:?set the Lakebase OAuth database user}"
: "${LAKEBASE_MIGRATION_PASSWORD:?set the generated Lakebase OAuth credential}"

export LAKEBASE_MIGRATION_DSN="postgresql://${LAKEBASE_MIGRATION_USER}:${LAKEBASE_MIGRATION_PASSWORD}@${LAKEBASE_MIGRATION_HOST}/databricks_postgres?sslmode=require"
