-- U-05 RATING_RESULTS -> Lakebase billing.rating_results (unit p1-rating-results, wave 3 batch a).
--
-- Oracle source: OW_BILLING.RATING_RESULTS (services/legacy-billing/db/oracle/schema/01_tables.sql).
--
-- OVERAGE_AMOUNT is NUMBER(12,2) and stays numeric(12,2): money never becomes a float, and the
-- scale is what makes pkg_rating's ROUND(...,2) reproducible on the target.
-- The four unit counters are NUMBER(10), which exceeds int4, so they are bigint.
-- CREATED_AT is an Oracle TIMESTAMP with no zone recorded. The mapping spec names timestamptz,
-- but the recon gate fails that: the source value is naive and a timestamptz target comes back
-- zone-aware, so tier 3 reports a field_diff on every row even though the wall clock matches
-- (2025-12-31 00:00 vs 2025-12-31 00:00+00). Wave 0 hit the same thing on
-- billing.billing_audit_log.logged_at and settled on a zone-less column
-- (w0a_pkg_ow_util.sql:127-141); this follows that precedent with timestamp(6), keeping Oracle's
-- default fractional-second precision rather than truncating to whole seconds. The UTC
-- assumption (plan decision P1-D3) is unchanged - it is declared, not stored.
-- The sibling DATE columns on rating_periods are timestamp(0): that difference is the source's.
--
-- Both Oracle foreign keys are reproduced with their original names. They are validated, not
-- cleaned: D8-01 requires orphans to survive the migration, and the fixture and live source
-- carry none for this table, so the constraints hold without dropping a row. billing.tenants,
-- billing.subscriptions (wave 2) and billing.rating_periods (unit p1-rating-periods) are read
-- by these references only; no DDL of theirs is touched here.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.rating_results (
    id              varchar(36)   NOT NULL,
    period_id       varchar(36)   NOT NULL,
    subscription_id varchar(36)   NOT NULL,
    used_units      bigint        NOT NULL,
    quota_units     bigint        NOT NULL,
    rollover_units  bigint        NOT NULL,
    billable_units  bigint        NOT NULL,
    overage_amount  numeric(12,2) NOT NULL,
    created_at      timestamp(6)  NOT NULL,
    CONSTRAINT pk_rating_results PRIMARY KEY (id),
    CONSTRAINT fk_rr_period FOREIGN KEY (period_id) REFERENCES billing.rating_periods (id),
    CONSTRAINT fk_rr_sub FOREIGN KEY (subscription_id) REFERENCES billing.subscriptions (id)
);

-- An earlier run of this script on the wave branch created created_at as timestamptz. The table
-- is this unit's own and empty until the load below, so bring it onto the zone-less type in
-- place rather than leaving two shapes behind on the branch.
ALTER TABLE billing.rating_results
    ALTER COLUMN created_at TYPE timestamp(6);

COMMENT ON TABLE billing.rating_results IS
    'Migration unit p1-rating-results (U-05) from Oracle OW_BILLING.RATING_RESULTS.';
COMMENT ON COLUMN billing.rating_results.id IS
    'Deterministic MD5 uuid from billing.f_md5_uuid(period_id), wave 0 parity proof.';
