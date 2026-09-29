-- PostgreSQL target: schemas and the DDL version ledger (CONTRACTS.md §8). Applied inside the tenant's
-- existing database (otterworks_<token>) on the shared RDS instance; every file here is idempotent.
-- source_key / key_from / key_to use COLLATE "C" so ranges and ORDER BY follow byte order, exactly as the job does.
CREATE SCHEMA IF NOT EXISTS mig;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS arch;

CREATE TABLE IF NOT EXISTS mig.schema_version (
    file_name       VARCHAR(128)    NOT NULL,
    file_sha256     CHAR(64)        NOT NULL,
    applied_at      TIMESTAMP(3)    NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
    CONSTRAINT pk_schema_version PRIMARY KEY (file_name)
);
