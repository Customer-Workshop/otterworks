#!/bin/bash
# This directory (db/oracle/startup) is mounted into /opt/oracle/scripts/startup,
# which the Oracle Free image runs on every boot once the database is open.
# (The image ships a prebuilt DB, so /opt/oracle/scripts/setup never fires —
# startup is the reliable hook.) Only this orchestrator lives here: anything
# else in the mounted directory would be auto-executed as SYSDBA in the CDB
# root, which is the wrong container for our schema.
#
# Idempotent and self-repairing: the completion marker is written only after
# every initialization script and object validity check succeeds. Every
# completed boot applies the idempotent static-data upgrade.
#
# The image *sources* startup scripts, so all work happens in a subshell to
# keep `set -e` and any failure from tearing down the container entrypoint.
(
  set -euo pipefail

  SQL_DIR=/opt/oracle/scripts/oracle-billing

  run_sql() {
    local conn="$1" file="$2"
    echo "== ${file} (${conn%%/*})"
    sqlplus -s "${conn}@localhost:1521/FREEPDB1" @"${file}"
  }

  table_marker=$(sqlplus -s "system/${ORACLE_PWD}@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT COUNT(*) FROM all_tables
 WHERE owner = 'OW_BILLING' AND table_name = 'FIXTURE_META';
EXIT;
SQL
  )
  table_marker=$(echo "${table_marker}" | tr -d '[:space:]')
  if [ "${table_marker}" = "1" ]; then
    column_marker=$(sqlplus -s "system/${ORACLE_PWD}@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT COUNT(*) FROM all_tab_columns
 WHERE owner = 'OW_BILLING'
   AND table_name = 'FIXTURE_META'
   AND column_name = 'MARKER';
EXIT;
SQL
    )
    column_marker=$(echo "${column_marker}" | tr -d '[:space:]')
    if [ "${column_marker}" = "0" ]; then
      echo "== oracle-billing fixture already initialized with old marker shape"
      run_sql "ow_billing/ow_billing" "${SQL_DIR}/schema/04_upgrade_static.sql"
      sqlplus -s "ow_billing/ow_billing@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
MERGE INTO fixture_meta target
USING (SELECT 'initialized' AS marker, '1' AS value FROM dual) source
   ON (target.marker = source.marker)
 WHEN MATCHED THEN
      UPDATE SET target.value = source.value,
                 target.initialized_at = SYSTIMESTAMP
 WHEN NOT MATCHED THEN
      INSERT (marker, value, initialized_at)
      VALUES (source.marker, source.value, SYSTIMESTAMP);
COMMIT;
EXIT;
SQL
      exit 0
    fi
    if [ "${column_marker}" != "1" ]; then
      echo "== could not determine FIXTURE_META marker shape: ${column_marker}" >&2
      exit 1
    fi
    initialized_marker=$(sqlplus -s "system/${ORACLE_PWD}@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT COUNT(*) FROM ow_billing.fixture_meta WHERE marker = 'initialized';
EXIT;
SQL
    )
    initialized_marker=$(echo "${initialized_marker}" | tr -d '[:space:]')
    case "${initialized_marker}" in
      1)
        echo "== oracle-billing fixture already initialized, applying static upgrade"
        run_sql "ow_billing/ow_billing" "${SQL_DIR}/schema/04_upgrade_static.sql"
        exit 0
        ;;
      0)
        echo "== oracle-billing fixture has a partial completion marker; repairing"
        ;;
      *) echo "== could not determine fixture completion state: ${initialized_marker}" >&2; exit 1 ;;
    esac
  elif [ "${table_marker}" != "0" ]; then
    echo "== could not determine FIXTURE_META table state: ${table_marker}" >&2
    exit 1
  fi

  user_exists=$(sqlplus -s "system/${ORACLE_PWD}@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT COUNT(*) FROM all_users WHERE username = 'OW_BILLING';
EXIT;
SQL
  )
  if [ "$(echo "${user_exists}" | tr -d '[:space:]')" = "0" ]; then
    run_sql "system/${ORACLE_PWD}" "${SQL_DIR}/setup/01_users.sql"
  else
    echo "== user exists without completion marker: repairing a partial init"
    sqlplus -s "system/${ORACLE_PWD}@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
DROP USER ow_billing CASCADE;
EXIT;
SQL
    run_sql "system/${ORACLE_PWD}" "${SQL_DIR}/setup/01_users.sql"
  fi

  run_sql "ow_billing/ow_billing" "${SQL_DIR}/schema/01_tables.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/schema/02_horror.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/packages/01_pkg_util.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/packages/02_pkg_plans.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/packages/03_pkg_rating.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/packages/04_pkg_invoicing.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/schema/03_seed_static.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/packages/05_pkg_dunning.sql"
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/schema/04_jobs.sql"

  # PL/SQL compilation errors do not trip WHENEVER SQLERROR, so assert every
  # object in the schema is VALID before declaring success.
  invalid=$(sqlplus -s "system/${ORACLE_PWD}@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT COUNT(*) FROM all_objects
 WHERE owner = 'OW_BILLING' AND status <> 'VALID';
EXIT;
SQL
  )
  invalid=$(echo "${invalid}" | tr -d '[:space:]')
  if [ "${invalid}" != "0" ]; then
    echo "== ${invalid} invalid object(s) after initialization" >&2
    sqlplus -s "system/${ORACLE_PWD}@localhost:1521/FREEPDB1" <<'SQL'
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT owner || '.' || object_name || ' (' || object_type || ')'
  FROM all_objects
 WHERE owner = 'OW_BILLING' AND status <> 'VALID';
EXIT;
SQL
    exit 1
  fi

  # Completion marker: written last; the health check and the skip guard
  # both key off the table.
  sqlplus -s "ow_billing/ow_billing@localhost:1521/FREEPDB1" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
CREATE TABLE fixture_meta (
    marker        VARCHAR2(100),
    value         VARCHAR2(100),
    initialized_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
MERGE INTO fixture_meta target
USING (SELECT 'initialized' AS marker, '1' AS value FROM dual) source
   ON (target.marker = source.marker)
 WHEN MATCHED THEN
      UPDATE SET target.value = source.value,
                 target.initialized_at = SYSTIMESTAMP
 WHEN NOT MATCHED THEN
      INSERT (marker, value, initialized_at)
      VALUES (source.marker, source.value, SYSTIMESTAMP);
COMMIT;
EXIT;
SQL
  run_sql "ow_billing/ow_billing" "${SQL_DIR}/schema/04_upgrade_static.sql"

  echo "== oracle-billing fixture ready"
) || echo "== oracle-billing fixture initialization FAILED (will retry on next boot; see errors above)"
