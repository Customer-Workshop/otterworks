-- U-10 NOTIFICATIONS -> Lakebase billing.notifications (unit p1-notifications, wave 3 batch d).
--
-- Oracle source: OW_BILLING.NOTIFICATIONS (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- Idempotent: every statement is CREATE ... IF NOT EXISTS (P1-D6).
--
-- Types follow the unit mapping spec: VARCHAR2(36) -> varchar(36); NUMBER(4) -> smallint
-- (kind_cd stays the magic number the application writes, billing.codes('NOTIF_KIND'):
-- 3 suspension).
--
-- sent_at deviates from the generated mapping spec, which proposes timestamptz: it is
-- timestamp(6) here, the zone-less type, matching Oracle TIMESTAMP's own precision.
-- P1-D3 is the reason - Oracle carries no zone, the migration assumes and declares UTC and
-- keeps the time part - and wave 0 already took the same decision for
-- billing.billing_audit_log.logged_at. It is also what the recon gate requires: the
-- canonicalization profile applies datetime_utc_truncate_ms to TIMESTAMP -> TIMESTAMP_NTZ
-- only, so a timestamptz column is compared under `identity` and a tz-aware target value
-- never equals the zone-less source value. Reported as a dialect finding on the mapping
-- generator (databricks/migration/tools/gen_mapping_specs.py:185), not retuned in recon.
--
-- Constraints: the primary key keeps its Oracle name, and so does UQ_NOTIFICATIONS
-- (tenant_id, kind_cd, sent_at) - the key behind pkg_dunning's NOT EXISTS dedupe, which is
-- what stops a second sweep on the same day sending a second suspension notice.
--
-- The Oracle foreign key fk_notif_tenant is deliberately NOT recreated (D8-01 orphans are
-- reproduced, and billing.tenants is another unit's load).

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.notifications (
    id        varchar(36) NOT NULL,
    tenant_id varchar(36) NOT NULL,
    kind_cd   smallint    NOT NULL,
    sent_at   timestamp(6) NOT NULL,
    CONSTRAINT pk_notifications PRIMARY KEY (id),
    CONSTRAINT uq_notifications UNIQUE (tenant_id, kind_cd, sent_at)
);

COMMENT ON TABLE billing.notifications IS
    'Migration unit p1-notifications (U-10) from Oracle OW_BILLING.NOTIFICATIONS.';
COMMENT ON COLUMN billing.notifications.kind_cd IS
    'Magic kind code, billing.codes(''NOTIF_KIND''): 1 invoice, 2 dunning, 3 suspension.';
COMMENT ON COLUMN billing.notifications.tenant_id IS
    'References billing.tenants(id) in the source; not enforced here, see D8-01 orphans.';
