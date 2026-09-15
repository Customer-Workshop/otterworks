-- U-09 DUNNING_ATTEMPTS -> Lakebase billing.dunning_attempts (unit p1-dunning-attempts,
-- wave 3 batch d).
--
-- Oracle source: OW_BILLING.DUNNING_ATTEMPTS (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- Idempotent: every statement is CREATE ... IF NOT EXISTS (P1-D6).
--
-- Types follow the unit mapping spec and the wave-1/2 dialect rules: VARCHAR2(36) ->
-- varchar(36); NUMBER(4) -> smallint (status_cd stays the magic number the application
-- writes, billing.codes('DUN_STATUS')); Oracle DATE carries a time part, so
-- scheduled_for is timestamp(0) and never date (P1-D3, UTC assumed and declared).
--
-- Constraints: the primary key keeps its Oracle name. UQ_DUNNING_ATTEMPTS
-- (invoice_id, attempt_no) is the key the scheduler leans on: pkg_dunning computes the next
-- attempt as MAX(attempt_no)+1 per invoice and lets a duplicate insert fail into
-- `WHEN OTHERS THEN NULL`, so the unique key is what makes a double run a no-op instead of
-- a second row. Oracle declares it on the table; it is declared here too, under the same
-- name, and named in the mapping.
--
-- Both Oracle foreign keys are recreated with the names, referenced columns and delete rule
-- the source declares (ALL_CONSTRAINTS on OW_BILLING: FK_DA_TENANT -> TENANTS(ID),
-- FK_DA_INVOICE -> INVOICES(ID), DELETE_RULE 'NO ACTION', NOT DEFERRABLE, VALIDATED).
-- Oracle has no ON UPDATE clause at all, so neither key carries one here. D8-01 keeps
-- orphan rows that exist inside the migrated data; it does not remove the source's
-- referential integrity, and the source has none to reproduce -- both keys are enabled and
-- validated on Oracle, so an orphan cannot exist there either.
-- billing.tenants and billing.invoices are referenced only: this unit adds no DDL to them.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.dunning_attempts (
    id            varchar(36)  NOT NULL,
    tenant_id     varchar(36)  NOT NULL,
    invoice_id    varchar(36)  NOT NULL,
    attempt_no    smallint     NOT NULL,
    scheduled_for timestamp(0) NOT NULL,
    status_cd     smallint     NOT NULL,
    CONSTRAINT pk_dunning_attempts PRIMARY KEY (id),
    CONSTRAINT uq_dunning_attempts UNIQUE (invoice_id, attempt_no)
);

-- Postgres has no ADD CONSTRAINT IF NOT EXISTS, so each key is guarded on pg_constraint to
-- keep the file rerunnable (P1-D6).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_da_tenant'
                      AND conrelid = 'billing.dunning_attempts'::regclass) THEN
        ALTER TABLE billing.dunning_attempts
            ADD CONSTRAINT fk_da_tenant FOREIGN KEY (tenant_id)
            REFERENCES billing.tenants (id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_da_invoice'
                      AND conrelid = 'billing.dunning_attempts'::regclass) THEN
        ALTER TABLE billing.dunning_attempts
            ADD CONSTRAINT fk_da_invoice FOREIGN KEY (invoice_id)
            REFERENCES billing.invoices (id);
    END IF;
END;
$$;

COMMENT ON TABLE billing.dunning_attempts IS
    'Migration unit p1-dunning-attempts (U-09) from Oracle OW_BILLING.DUNNING_ATTEMPTS.';
COMMENT ON COLUMN billing.dunning_attempts.status_cd IS
    'Magic status code, billing.codes(''DUN_STATUS''): 10 scheduled, 20 sent, 30 skipped.';
COMMENT ON COLUMN billing.dunning_attempts.attempt_no IS
    'Sequential per invoice; unique with invoice_id (uq_dunning_attempts).';
COMMENT ON COLUMN billing.dunning_attempts.tenant_id IS
    'References billing.tenants(id), enforced by fk_da_tenant as Oracle declares it.';
COMMENT ON COLUMN billing.dunning_attempts.invoice_id IS
    'References billing.invoices(id), enforced by fk_da_invoice as Oracle declares it.';
