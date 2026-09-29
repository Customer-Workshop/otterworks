-- Snowflake account-level bootstrap for the legacy data migration (SNOWFLAKE-PORT-SPEC.md §4). Run ONCE per
-- account as ACCOUNTADMIN (bootstrap.py --account, or paste into a worksheet). Idempotent.
--
-- Creates the administrative role every tenant object hangs off and the single XSMALL warehouse all runs share.
-- Nothing here is per tenant and nothing here is granted to a user except the operator named by {{ADMIN_USER}};
-- per-tenant databases and job roles come from tenant.sql.
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS LDM_ADMIN
    COMMENT = 'otterworks ldm: owns the per-tenant OTTERWORKS_LDM_<TOKEN> databases and LDM_JOB_<TOKEN> roles';
GRANT ROLE LDM_ADMIN TO ROLE SYSADMIN;
GRANT CREATE DATABASE ON ACCOUNT TO ROLE LDM_ADMIN;
GRANT CREATE ROLE ON ACCOUNT TO ROLE LDM_ADMIN;

-- One warehouse for every tenant: XSMALL, suspends after 60 s idle, resumes on the first COPY/SELECT of a run.
-- INITIALLY_SUSPENDED so the bootstrap itself bills nothing.
CREATE WAREHOUSE IF NOT EXISTS LDM_WH WITH
    WAREHOUSE_SIZE = XSMALL
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    MIN_CLUSTER_COUNT = 1
    MAX_CLUSTER_COUNT = 1
    STATEMENT_TIMEOUT_IN_SECONDS = 3600
    COMMENT = 'otterworks ldm: shared XSMALL warehouse for COPY INTO / validation / promotion';
GRANT OWNERSHIP ON WAREHOUSE LDM_WH TO ROLE LDM_ADMIN COPY CURRENT GRANTS;

-- Cap the bill: a resource monitor on the warehouse suspends it at the monthly quota (credits, spec §5).
CREATE RESOURCE MONITOR IF NOT EXISTS LDM_WH_MONITOR WITH
    CREDIT_QUOTA = {{CREDIT_QUOTA}}
    FREQUENCY = MONTHLY
    START_TIMESTAMP = IMMEDIATELY
    TRIGGERS ON 80 PERCENT DO NOTIFY
             ON 100 PERCENT DO SUSPEND_IMMEDIATE;
ALTER WAREHOUSE LDM_WH SET RESOURCE_MONITOR = LDM_WH_MONITOR;

GRANT ROLE LDM_ADMIN TO USER {{ADMIN_USER}};
