-- Snowflake per-tenant bootstrap (SNOWFLAKE-PORT-SPEC.md §4): one database and one job role per demo token,
-- created by LDM_ADMIN (account.sql) from scripts/deploy-demo.sh via bootstrap.py --tenant <token>. Idempotent.
--
-- Tenant isolation is by object ownership: LDM_JOB_{{TOKEN}} owns OTTERWORKS_LDM_{{TOKEN}} and holds nothing
-- else, so a Job running as that role cannot read or write another tenant's database (the Snowflake
-- counterpart of the per-tenant PostgreSQL database and the IRSA-scoped S3 prefix). `ldm init` creates the
-- MIG/STG/ARCH schemas and tables inside the database (../*.sql); nothing here knows the table shapes.
USE ROLE LDM_ADMIN;

CREATE ROLE IF NOT EXISTS LDM_JOB_{{TOKEN}}
    COMMENT = 'otterworks ldm tenant {{NAMESPACE}}: the migration Job; owns OTTERWORKS_LDM_{{TOKEN}} only';
GRANT ROLE LDM_JOB_{{TOKEN}} TO ROLE LDM_ADMIN;
GRANT USAGE ON WAREHOUSE LDM_WH TO ROLE LDM_JOB_{{TOKEN}};

CREATE DATABASE IF NOT EXISTS OTTERWORKS_LDM_{{TOKEN}}
    DATA_RETENTION_TIME_IN_DAYS = 1
    COMMENT = 'otterworks ldm tenant {{NAMESPACE}}: STG/ARCH/MIG archive store (control plane stays in PostgreSQL)';
GRANT OWNERSHIP ON SCHEMA OTTERWORKS_LDM_{{TOKEN}}.PUBLIC TO ROLE LDM_JOB_{{TOKEN}} COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DATABASE OTTERWORKS_LDM_{{TOKEN}} TO ROLE LDM_JOB_{{TOKEN}} COPY CURRENT GRANTS;

-- The Job authenticates as this user with a programmatic access token restricted to the tenant role.
GRANT ROLE LDM_JOB_{{TOKEN}} TO USER {{JOB_USER}};
