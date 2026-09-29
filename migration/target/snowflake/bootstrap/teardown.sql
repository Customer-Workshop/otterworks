-- Snowflake per-tenant teardown: drops the tenant database and job role (bootstrap.py --teardown <token>,
-- called by scripts/teardown-tenant.sh). LDM_ADMIN, LDM_WH and the resource monitor stay for the next tenant.
USE ROLE LDM_ADMIN;
DROP DATABASE IF EXISTS OTTERWORKS_LDM_{{TOKEN}};
DROP ROLE IF EXISTS LDM_JOB_{{TOKEN}};
