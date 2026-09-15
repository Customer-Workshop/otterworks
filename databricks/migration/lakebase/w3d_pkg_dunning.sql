-- U-24 pkg_dunning -> Lakebase billing routines (unit p1-pkg-dunning, wave 3 batch d).
--
-- Oracle source: services/legacy-billing/db/oracle/packages/05_pkg_dunning.sql.
-- Three public members, one routine each (Oracle package -> Postgres schema):
--   fn_overdue_accounts  SYS_REFCURSOR -> RETURNS TABLE
--   sp_schedule_dunning  PROCEDURE
--   sp_suspend_overdue   PROCEDURE
-- Every statement is CREATE OR REPLACE, so re-applying the file is a no-op.
--
-- Package state (P1-D4). The Oracle package keeps g_last_run_dt and g_scheduled_cnt as
-- package globals. They become INOUT parameters on sp_schedule_dunning, not a session
-- global and not a state table: a state table would be a write target this batch has not
-- declared. Callers that ignore them (the wave-4 job U-25) call the procedure with the
-- as-of date alone.
--
-- Logging is deliberately dropped. Oracle calls pkg_ow_util.log_msg, whose converted form
-- billing.log_msg inserts into billing.billing_audit_log - a table outside this batch's
-- declared write targets. The log line is not observable behaviour for recon, so the
-- routines stay silent and the gap is declared in the PR rather than routed around.
--
-- Read dependency: billing.invoices is migrated by unit p1-invoices (batch w3-b, running
-- concurrently) and is not on the wave branch yet. plpgsql resolves table references at
-- execution time, so these routines install now and run once w3-b lands; the end-to-end
-- op diff is the wave gate's, after that merge.

CREATE SCHEMA IF NOT EXISTS billing;

-- fn_overdue_accounts: the Oracle cursor's column names, order and row order, unchanged.
-- Conversions: the `(+)` outer join becomes an ANSI LEFT JOIN (tenants is the optional
-- side, so a tenant-less invoice still appears, with tenant_status 'UNKNOWN' - D8-01
-- orphans are reproduced); DECODE becomes CASE; the TO_CHAR(...,'YYYYMMDD') string compare
-- becomes a date compare, which is the same predicate because the format sorts
-- lexicographically in date order; days_overdue keeps Oracle's TRUNC-TRUNC whole-day
-- difference. ORDER BY issued_at, id is part of the contract: recon compares row order.
CREATE OR REPLACE FUNCTION billing.fn_overdue_accounts(p_as_of timestamp(0))
RETURNS TABLE (
    tenant_id     varchar(36),
    invoice_id    varchar(36),
    total         numeric(12,2),
    days_overdue  integer,
    tenant_status text
)
LANGUAGE sql
STABLE
-- Oracle has no session zone; P1-D3 declares the estate UTC. billing.invoices is w3-b's
-- and its mapping still types issued_at as timestamptz, so a date cast would otherwise
-- follow the caller's TimeZone. Pinning it here makes the business date UTC whichever
-- type that column lands as, and whatever the caller's session is set to.
SET TimeZone TO 'UTC'
AS $$
    SELECT i.tenant_id,
           i.id AS invoice_id,
           i.total,
           (p_as_of::date - i.issued_at::date)::integer AS days_overdue,
           CASE t.status_cd
               WHEN 10 THEN 'active'
               WHEN 20 THEN 'suspended'
               ELSE 'UNKNOWN'
           END AS tenant_status
      FROM billing.invoices i
      LEFT JOIN billing.tenants t ON t.id = i.tenant_id
     WHERE i.status_cd = 40
       AND i.issued_at::date < p_as_of::date
     ORDER BY i.issued_at, i.id
$$;

-- sp_schedule_dunning: one dunning attempt per open invoice, oldest first.
--
-- Behaviour kept as-is:
--  * attempt_no is COALESCE(MAX(attempt_no),0)+1 read per invoice, inside the loop, so an
--    invoice already carrying attempts gets the next number;
--  * the id is billing.f_md5_uuid(invoice_id || attempt_no), the same input string Oracle
--    builds, so a rerun computes the same key;
--  * the weekend shift moves a Saturday run to Monday (+2) and a Sunday run to Monday (+1).
--    Oracle spells it TO_CHAR(d,'DY','NLS_DATE_LANGUAGE=ENGLISH'); Postgres to_char would
--    follow lc_time instead, so this uses EXTRACT(ISODOW) - 6 Saturday, 7 Sunday - which
--    carries no locale at all;
--  * every insert runs in its own BEGIN/EXCEPTION WHEN OTHERS THEN NULL block. That is the
--    swallow at :63-66 and it is reproduced, not fixed (P1-D2): a duplicate
--    (invoice_id, attempt_no) - or any other error on the row - silently schedules one
--    attempt fewer, and the recon baseline is the rows the run actually wrote;
--  * p_scheduled_cnt counts only the inserts that survived, as g_scheduled_cnt does.
CREATE OR REPLACE PROCEDURE billing.sp_schedule_dunning(
    IN    p_as_of         timestamp(0),
    INOUT p_scheduled_cnt integer      DEFAULT 0,
    INOUT p_last_run_dt   timestamp(0) DEFAULT NULL
)
LANGUAGE plpgsql
SET TimeZone TO 'UTC'          -- UTC business dates regardless of the caller (P1-D3)
AS $$
DECLARE
    v_attempt smallint;
    v_next    timestamp(0);
    v_inv     record;
BEGIN
    p_last_run_dt := p_as_of;
    p_scheduled_cnt := 0;

    FOR v_inv IN
        SELECT id, tenant_id
          FROM billing.invoices
         WHERE status_cd = 40
         ORDER BY issued_at, id
    LOOP
        SELECT COALESCE(MAX(attempt_no), 0) + 1
          INTO v_attempt
          FROM billing.dunning_attempts
         WHERE invoice_id = v_inv.id;

        v_next := date_trunc('day', p_as_of);
        v_next := v_next + (CASE EXTRACT(ISODOW FROM v_next)
                                WHEN 6 THEN 2
                                WHEN 7 THEN 1
                                ELSE 0
                            END) * INTERVAL '1 day';

        BEGIN
            INSERT INTO billing.dunning_attempts (
                id, tenant_id, invoice_id, attempt_no, scheduled_for, status_cd
            ) VALUES (
                billing.f_md5_uuid(v_inv.id || v_attempt::text),
                -- Oracle widens the count in an unrestricted NUMBER and then inserts it
                -- into NUMBER(4): attempt 10000 raises inside the swallow and schedules
                -- nothing. smallint would take it, so the four-digit bound is restated.
                v_inv.tenant_id, v_inv.id, v_attempt::numeric(4,0), v_next, 10
            );
            p_scheduled_cnt := p_scheduled_cnt + 1;
        EXCEPTION
            WHEN OTHERS THEN
                NULL;  -- legacy swallow, reproduced (P1-D2)
        END;
    END LOOP;
END;
$$;

-- sp_suspend_overdue: suspend tenants whose open invoices are 14+ days old.
--
-- Runtime writes into tables another unit owns the DDL for, declared in the PR:
-- billing.tenants and billing.subscriptions (DML only, never DDL).
--
-- Behaviour kept as-is: the driving set is DISTINCT tenant_id over invoices whose issued_at
-- day is on or before as-of minus 14 days; a tenant is skipped unless it is currently
-- status 10; subscriptions move to 20 with suspended_on = the as-of day; the suspension
-- notification is kind 3 at midnight of the as-of day, guarded by the same NOT EXISTS on
-- (tenant_id, kind_cd, sent_at), which is what makes a second sweep on the same day write
-- nothing.
CREATE OR REPLACE PROCEDURE billing.sp_suspend_overdue(IN p_as_of timestamp(0))
LANGUAGE plpgsql
SET TimeZone TO 'UTC'          -- UTC business dates regardless of the caller (P1-D3)
AS $$
DECLARE
    v_active  integer;
    v_tenant  record;
    v_sent_at timestamp(0) := date_trunc('day', p_as_of);
BEGIN
    FOR v_tenant IN
        SELECT DISTINCT i.tenant_id
          FROM billing.invoices i
         WHERE i.status_cd = 40
           AND i.issued_at::date <= (date_trunc('day', p_as_of) - INTERVAL '14 days')::date
    LOOP
        SELECT COUNT(*)
          INTO v_active
          FROM billing.tenants
         WHERE id = v_tenant.tenant_id AND status_cd = 10;

        IF v_active > 0 THEN
            UPDATE billing.tenants
               SET status_cd = 20
             WHERE id = v_tenant.tenant_id;

            UPDATE billing.subscriptions
               SET status_cd = 20,
                   suspended_on = date_trunc('day', p_as_of)
             WHERE tenant_id = v_tenant.tenant_id AND status_cd = 10;

            INSERT INTO billing.notifications (id, tenant_id, kind_cd, sent_at)
            SELECT billing.f_md5_uuid(v_tenant.tenant_id || 'suspension' ||
                       to_char(date_trunc('day', p_as_of), 'YYYY-MM-DD')),
                   v_tenant.tenant_id, 3, v_sent_at
             WHERE NOT EXISTS (
                   SELECT 1 FROM billing.notifications
                    WHERE tenant_id = v_tenant.tenant_id
                      AND kind_cd = 3
                      AND sent_at = v_sent_at);
        END IF;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION billing.fn_overdue_accounts(timestamp(0)) IS
    'Migration unit p1-pkg-dunning (U-24) from Oracle pkg_dunning.fn_overdue_accounts.';
COMMENT ON PROCEDURE billing.sp_schedule_dunning(timestamp(0), integer, timestamp(0)) IS
    'Migration unit p1-pkg-dunning (U-24); package state returned as INOUT (P1-D4).';
COMMENT ON PROCEDURE billing.sp_suspend_overdue(timestamp(0)) IS
    'Migration unit p1-pkg-dunning (U-24); runtime DML on billing.tenants/subscriptions.';
