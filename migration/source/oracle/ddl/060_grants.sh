#!/bin/bash
# Object grants for the migration login ($APP_USER, created by the image entrypoint before this runs).
# The same account seeds the estate, extracts, and purges - like the Db2 stand-in's db2inst1.
# Runs as a new shell process (file is executable) inside the container on first start.
set -Eeuo pipefail
: "${APP_USER:?APP_USER must be set (the migration login)}"
sqlplus -s / as sysdba <<SQL
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER SESSION SET CONTAINER = FREEPDB1;
GRANT SELECT, INSERT, DELETE ON ARCHIVE.RETNPLCY TO ${APP_USER};
GRANT SELECT, INSERT, DELETE ON ARCHIVE.DOCARCH  TO ${APP_USER};
GRANT SELECT, INSERT, DELETE ON ARCHIVE.FILEAUD  TO ${APP_USER};
GRANT SELECT, INSERT         ON MIGAUDIT.PURGE_AUDIT TO ${APP_USER};
EXIT
SQL
