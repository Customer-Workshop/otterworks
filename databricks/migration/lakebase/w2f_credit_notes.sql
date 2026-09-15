-- U-08 CREDIT_NOTES -> Lakebase billing.credit_notes (unit p1-credit-notes, wave 2 batch f).
--
-- Oracle source: OW_BILLING.CREDIT_NOTES (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- Idempotent: every statement is CREATE ... IF NOT EXISTS (P1-D6).
--
-- Types follow the unit mapping spec and the wave-1 dialect rules:
--   VARCHAR2(36) -> varchar(36); NUMBER(12,2) -> numeric(12,2), never float; Oracle DATE
--   carries a time part, so issued_on is timestamp(0) and never date (P1-D3, UTC assumed
--   and declared).
--
-- Constraints: both Oracle constraints are recreated under their Oracle names. fk_cn_tenant
-- is enforced in the source and the source carries no orphan credit note (checked on the
-- fixture and on the live read), so reproducing it does not conflict with D8-01; the parent
-- billing.tenants merged in wave 1. No constraint Oracle does not have is added.
--
-- Indexes: the source table has exactly one index, the implicit unique index behind
-- PK_CREDIT_NOTES. Postgres creates the same index for the primary key, so there is no
-- separate CREATE INDEX. No covering index for the burn-down scan is added - it does not
-- exist on Oracle, and this table holds 5 rows.
--
-- Ordering contract for wave 3 (w3-b invoicing burn-down), see w2f_credit_notes.md:
--   SELECT id, remaining_amount FROM billing.credit_notes
--    WHERE tenant_id = ? AND remaining_amount > 0 ORDER BY issued_on, id
-- must stay oldest-first on (issued_on, id). The burn-down itself is NOT implemented here.

-- The billing schema and billing.tenants are wave-1 objects and must already exist; this
-- unit creates neither, so a missing prerequisite fails here instead of being papered over.

CREATE TABLE IF NOT EXISTS billing.credit_notes (
    id               varchar(36)   NOT NULL,
    tenant_id        varchar(36)   NOT NULL,
    issued_on        timestamp(0)  NOT NULL,
    amount           numeric(12,2) NOT NULL,
    remaining_amount numeric(12,2) NOT NULL,
    CONSTRAINT pk_credit_notes PRIMARY KEY (id),
    CONSTRAINT fk_cn_tenant FOREIGN KEY (tenant_id) REFERENCES billing.tenants (id)
);

COMMENT ON TABLE billing.credit_notes IS
    'Migration unit p1-credit-notes (U-08) from Oracle OW_BILLING.CREDIT_NOTES. Wave 3 burns '
    'these rows down in (issued_on, id) order; see w2f_credit_notes.md.';
COMMENT ON COLUMN billing.credit_notes.issued_on IS
    'Oracle DATE with its time part, timestamp(0), UTC assumed and declared (P1-D3). First '
    'key of the burn-down order.';
COMMENT ON COLUMN billing.credit_notes.remaining_amount IS
    'Open credit still to consume, numeric(12,2) exact. Wave 3 (w3-b) decrements it; nothing '
    'in wave 2 writes it after the load.';
