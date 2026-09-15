-- U-01 TENANTS -> Lakebase billing.tenants (unit p1-tenants, wave 1 batch a).
--
-- Oracle source: OW_BILLING.TENANTS (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- Shape is preserved, not improved: VARCHAR2(36) surrogate key stays a string key, the
-- CHAR(1) Y/N flag stays CHAR(1) (blank-padded semantics included), and STATUS_CD stays the
-- magic number the application writes (10 active / 20 suspended, resolved through
-- billing.codes at read time, enforced by nothing - same as Oracle).
--
-- Both Oracle constraints come across with their original names so a reader can match them
-- to the legacy schema: the primary key on ID and the unique key on NAME. Oracle and Postgres
-- both index a primary/unique key implicitly, so the unit needs no separate index.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.tenants (
    id            varchar(36)  NOT NULL,
    name          varchar(200) NOT NULL,
    tax_exempt_yn char(1)      DEFAULT 'N' NOT NULL,
    status_cd     smallint     NOT NULL,
    CONSTRAINT pk_tenants PRIMARY KEY (id),
    CONSTRAINT uq_tenants_name UNIQUE (name)
);

COMMENT ON TABLE billing.tenants IS
    'Migration unit p1-tenants (U-01) from Oracle OW_BILLING.TENANTS.';
COMMENT ON COLUMN billing.tenants.status_cd IS
    'Magic status code, billing.codes(''TENANT_STATUS''): 10 active, 20 suspended.';
