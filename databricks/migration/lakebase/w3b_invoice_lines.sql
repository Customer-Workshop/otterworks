-- U-07 INVOICE_LINES (modern) -> Lakebase billing.invoice_lines (unit p1-invoice-lines,
-- wave 3 batch b).
--
-- Oracle source: OW_BILLING.INVOICE_LINES (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- MODERN generation (D9-01): the legacy INVOICE_LINE table (singular, 150k rows with 37
-- orphans) went to Delta in wave 1 and is a different object. This one has two rows and no
-- orphan.
-- Idempotent: CREATE ... IF NOT EXISTS (P1-D6).
--
-- Types: VARCHAR2 -> varchar of the same length; NUMBER(6) -> integer (Oracle's range fits
-- and no fractional value can be stored); NUMBER(12,2) -> numeric(12,2), exact money, never
-- float; line_type stays free text, since Oracle has no check constraint on it.
--
-- Prerequisite: billing.invoices, created by unit p1-invoices in this same batch (PR
-- "p1-invoices (U-06)"). It exists on the wave branch; on a fresh branch apply
-- w3b_invoices.sql first. This unit does not create it - creating another unit's table to
-- satisfy a foreign key is exactly the substitute DDL the wave forbids.

CREATE TABLE IF NOT EXISTS billing.invoice_lines (
    id          varchar(36)   NOT NULL,
    invoice_id  varchar(36)   NOT NULL,
    line_no     integer       NOT NULL,
    line_type   varchar(10)   NOT NULL,
    description varchar(400)  NOT NULL,
    amount      numeric(12,2) NOT NULL,
    CONSTRAINT pk_invoice_lines PRIMARY KEY (id),
    CONSTRAINT uq_invoice_lines UNIQUE (invoice_id, line_no),
    CONSTRAINT fk_il_invoice FOREIGN KEY (invoice_id)
        REFERENCES billing.invoices (id) ON DELETE CASCADE
);

COMMENT ON TABLE billing.invoice_lines IS
    'Migration unit p1-invoice-lines (U-07) from Oracle OW_BILLING.INVOICE_LINES, the modern '
    'invoice generation (D9-01) - not legacy INVOICE_LINE.';
COMMENT ON COLUMN billing.invoice_lines.line_type IS
    'Free text on both sides: Oracle declares VARCHAR2(10) with no check constraint, so the '
    'values pkg_invoicing writes (BASE, OVERAGE, CREDIT) are convention, not a domain.';
