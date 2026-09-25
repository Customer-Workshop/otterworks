#!/usr/bin/env bash
# ------------------------------------------------------------------------------
# Post-apply T-SQL for the per-namespace Azure SQL database (called by null_resource.sql_init).
#
#  1. applies migration/target/sql/*.sql in file-name order (idempotent, GO-batched)
#  2. creates the contained reader user (Container Apps) in role ldm_report_reader
#  3. creates the user-assigned identity as an external user with
#     db_datareader / db_datawriter / db_ddladmin (Entra auth as the deploying SP)
#
# Inputs (env): SQL_SERVER_FQDN SQL_DATABASE SQL_ADMIN_USER SQL_ADMIN_PASSWORD
#               SQL_READER_USER SQL_READER_PASSWORD IDENTITY_NAME IDENTITY_CLIENT_ID DDL_DIR
#               AAD_CLIENT_ID AAD_TENANT_ID ARM_CLIENT_SECRET
# Tooling: go-sqlcmd (https://github.com/microsoft/go-sqlcmd) on PATH, or docker
#          (mcr.microsoft.com/mssql-tools, the only sqlcmd image MCR publishes - SQL auth only,
#          step 3 is then skipped).
# Never prints a secret.
# ------------------------------------------------------------------------------
set -euo pipefail

: "${SQL_SERVER_FQDN:?}" "${SQL_DATABASE:?}" "${SQL_ADMIN_USER:?}" "${SQL_ADMIN_PASSWORD:?}"
: "${SQL_READER_USER:?}" "${SQL_READER_PASSWORD:?}" "${IDENTITY_NAME:?}" "${IDENTITY_CLIENT_ID:?}" "${DDL_DIR:?}"

log() { echo "[apply-sql] $*" >&2; }

RETRIES="${SQL_CONNECT_RETRIES:-12}"
TOOLS_IMAGE="${MSSQL_TOOLS_IMAGE:-mcr.microsoft.com/mssql-tools:latest}"
TOOLS_SQLCMD="${MSSQL_TOOLS_SQLCMD:-/opt/mssql-tools/bin/sqlcmd}"

mode=""
if command -v sqlcmd >/dev/null 2>&1 && sqlcmd --version 2>/dev/null | grep -q 'Version: v'; then
  mode="go-sqlcmd"
elif command -v docker >/dev/null 2>&1; then
  mode="docker"
else
  log "neither go-sqlcmd nor docker found; skipping schema apply (ldm init will apply the DDL)"
  exit 0
fi
log "using $mode against ${SQL_SERVER_FQDN}/${SQL_DATABASE}"

# run_sql <auth: sql|aad> <file>
run_sql() {
  local auth="$1" file="$2"
  case "$mode:$auth" in
    go-sqlcmd:sql)
      SQLCMDPASSWORD="$SQL_ADMIN_PASSWORD" sqlcmd -S "tcp:${SQL_SERVER_FQDN},1433" -d "$SQL_DATABASE" \
        -U "$SQL_ADMIN_USER" -N -C -b -l 60 -i "$file" ;;
    go-sqlcmd:aad)
      SQLCMDPASSWORD="${ARM_CLIENT_SECRET:?ARM_CLIENT_SECRET is required for Entra auth}" \
        sqlcmd -S "tcp:${SQL_SERVER_FQDN},1433" -d "$SQL_DATABASE" \
        --authentication-method ActiveDirectoryServicePrincipal \
        -U "${AAD_CLIENT_ID:?}@${AAD_TENANT_ID:?}" -N -C -b -l 60 -i "$file" ;;
    docker:sql)
      docker run --rm -e SQLCMDPASSWORD="$SQL_ADMIN_PASSWORD" -v "$(dirname "$file"):/sql:ro" "$TOOLS_IMAGE" \
        "$TOOLS_SQLCMD" -S "tcp:${SQL_SERVER_FQDN},1433" -d "$SQL_DATABASE" \
        -U "$SQL_ADMIN_USER" -N -C -b -l 60 -i "/sql/$(basename "$file")" ;;
    *)
      return 99 ;;
  esac
}

# A serverless database resumes on first connection (40613); retry with backoff.
run_sql_retry() {
  local auth="$1" file="$2" n=1
  until run_sql "$auth" "$file"; do
    rc=$?
    if [ "$rc" -eq 99 ]; then return 99; fi
    if [ "$n" -ge "$RETRIES" ]; then
      log "giving up on $(basename "$file") after $n attempts"
      return "$rc"
    fi
    log "attempt $n failed (rc=$rc), retrying in 20s"
    n=$((n + 1)); sleep 20
  done
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# 1. schema files in name order
for f in "$DDL_DIR"/*.sql; do
  log "applying $(basename "$f")"
  cp "$f" "$work/ddl.sql"
  run_sql_retry sql "$work/ddl.sql"
done

# 2. contained reader user. The password is rendered into a 0600 file under the private temp dir
#    (never on a command line, never echoed).
escaped_pw="${SQL_READER_PASSWORD//\'/\'\'}"
umask 077
cat >"$work/reader.sql" <<EOF
IF DATABASE_PRINCIPAL_ID(N'${SQL_READER_USER}') IS NULL
    EXEC (N'CREATE USER [${SQL_READER_USER}] WITH PASSWORD = N''${escaped_pw}''');
ELSE
    EXEC (N'ALTER USER [${SQL_READER_USER}] WITH PASSWORD = N''${escaped_pw}''');
GO
IF IS_ROLEMEMBER(N'ldm_report_reader', N'${SQL_READER_USER}') = 0
    ALTER ROLE ldm_report_reader ADD MEMBER [${SQL_READER_USER}];
GO
EOF
umask 022
log "creating reader user ${SQL_READER_USER}"
run_sql_retry sql "$work/reader.sql"
rm -f "$work/reader.sql"

# 3. managed identity as an external user (needs Entra auth; SQL logins cannot create external users)
if [ "$mode" != "go-sqlcmd" ]; then
  log "docker mode: skipping external-provider user for ${IDENTITY_NAME} (run with go-sqlcmd, or let ldm init do it)"
  exit 0
fi
sid_hex="$(python3 - "$IDENTITY_CLIENT_ID" <<'EOF' 2>/dev/null || true
import sys, uuid
print("0x" + uuid.UUID(sys.argv[1]).bytes_le.hex().upper())
EOF
)"
cat >"$work/identity.sql" <<EOF
IF DATABASE_PRINCIPAL_ID(N'${IDENTITY_NAME}') IS NULL
BEGIN
    BEGIN TRY
        EXEC (N'CREATE USER [${IDENTITY_NAME}] FROM EXTERNAL PROVIDER');
    END TRY
    BEGIN CATCH
        -- Graph lookup unavailable (server identity lacks Directory Readers): bind by client-id SID instead.
        EXEC (N'CREATE USER [${IDENTITY_NAME}] WITH SID = ${sid_hex}, TYPE = E');
    END CATCH
END
GO
IF IS_ROLEMEMBER(N'db_datareader', N'${IDENTITY_NAME}') = 0 ALTER ROLE db_datareader ADD MEMBER [${IDENTITY_NAME}];
IF IS_ROLEMEMBER(N'db_datawriter', N'${IDENTITY_NAME}') = 0 ALTER ROLE db_datawriter ADD MEMBER [${IDENTITY_NAME}];
IF IS_ROLEMEMBER(N'db_ddladmin',  N'${IDENTITY_NAME}') = 0 ALTER ROLE db_ddladmin  ADD MEMBER [${IDENTITY_NAME}];
GO
EOF
log "granting ${IDENTITY_NAME} db_datareader/db_datawriter/db_ddladmin (Entra auth)"
run_sql_retry aad "$work/identity.sql"
log "done"
