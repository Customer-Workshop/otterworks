-- U-06 INVOICES (modern) -> Lakebase billing.invoices (unit p1-invoices, wave 3 batch b).
--
-- Oracle source: OW_BILLING.INVOICES (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- This is the MODERN invoice generation (D9-01). It is not the legacy INVOICE_HEADER /
-- INVOICE_LINE pair migrated to Delta in wave 1; the two generations coexist in the source
-- and are migrated to different targets.
-- Idempotent: every statement is CREATE ... IF NOT EXISTS (P1-D6).
--
-- Types follow the unit mapping spec and the wave-1 dialect rules:
--   VARCHAR2(36) -> varchar(36); NUMBER(12,2) -> numeric(12,2), never float, so the money
--   columns compare exactly; NUMBER(4) -> smallint with the magic status code kept as the
--   number the application writes (billing.codes('INV_STATUS') resolves it at read time,
--   enforced by nothing - same as Oracle); TIMESTAMP -> timestamp(6) (no zone), UTC assumed
--   and declared (P1-D3).
--
-- issued_at is timestamp(6), not timestamptz, under ledger decision D-010: Oracle TIMESTAMP
-- is zoneless, so a timestamptz target reads back zone-aware and no longer equals the naive
-- source value (every row became a Tier-3 field_diff on the first run of this unit). Wave 0
-- had already made the same correction by hand for billing_audit_log
-- (w0a_pkg_ow_util.sql:127). The instant is unchanged and UTC stays the declared
-- assumption. Oracle's default TIMESTAMP precision is 6, which timestamp(6) keeps.
--
-- Constraints: pk_invoices and fk_inv_tenant are recreated under their Oracle names. The
-- source enforces fk_inv_tenant and holds no orphan invoice (checked on the fixture and on
-- the live read), so reproducing it does not collide with D8-01.
-- fk_inv_period (period_id -> rating_periods) is NOT recreated here: rating_periods is a
-- wave-3 batch a object and is not on this branch, and creating another unit's table to
-- hang a constraint on would be a write outside this batch's declared targets. The column
-- and its values are carried across unchanged; the constraint is a wave-gate item once the
-- rating unit merges. Nothing Oracle does not have is added.
--
-- Indexes: the source has only the implicit unique index behind PK_INVOICES, which the
-- Postgres primary key provides. No extra index is invented.

-- The billing schema and billing.tenants are wave-1 objects and must already exist; this
-- unit creates neither, so a missing prerequisite fails here instead of being papered over.

CREATE TABLE IF NOT EXISTS billing.invoices (
    id        varchar(36)   NOT NULL,
    tenant_id varchar(36)   NOT NULL,
    period_id varchar(36)   NOT NULL,
    issued_at timestamp(6)  NOT NULL,
    subtotal  numeric(12,2) NOT NULL,
    tax       numeric(12,2) NOT NULL,
    total     numeric(12,2) NOT NULL,
    status_cd smallint      NOT NULL,
    CONSTRAINT pk_invoices PRIMARY KEY (id),
    CONSTRAINT fk_inv_tenant FOREIGN KEY (tenant_id) REFERENCES billing.tenants (id)
);

-- An earlier run of this script on the wave branch created issued_at as timestamptz, before
-- D-010 settled the rule. Bring an already-created table onto the zoneless type in place;
-- the stored instants are UTC, so the cast changes no value.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'billing' AND table_name = 'invoices'
                 AND column_name = 'issued_at' AND data_type = 'timestamp with time zone')
    THEN
        ALTER TABLE billing.invoices
            ALTER COLUMN issued_at TYPE timestamp(6) USING issued_at AT TIME ZONE 'UTC';
    END IF;
END;
$$;

COMMENT ON TABLE billing.invoices IS
    'Migration unit p1-invoices (U-06) from Oracle OW_BILLING.INVOICES, the modern invoice '
    'generation (D9-01) - not legacy INVOICE_HEADER.';
COMMENT ON COLUMN billing.invoices.period_id IS
    'Rating period key. Oracle enforces fk_inv_period against RATING_PERIODS; that parent '
    'table belongs to the concurrent rating unit and is not on this branch, so the '
    'constraint is deferred to the wave gate.';
COMMENT ON COLUMN billing.invoices.issued_at IS
    'Oracle TIMESTAMP, zoneless on both sides (D-010); UTC assumed and declared (P1-D3).';
COMMENT ON COLUMN billing.invoices.status_cd IS
    'Magic status code, billing.codes(''INV_STATUS''). 20 is what the issuing procedure '
    'writes; no check constraint exists on either side.';
