-- Unit p1-job-purge-audit-log (U-26): the converted body of the legacy JOB_PURGE_AUDIT_LOG.
--
-- Legacy source (services/legacy-billing/db/oracle/schema/04_jobs.sql:21-31), a
-- DBMS_SCHEDULER PLSQL_BLOCK job, FREQ=DAILY;BYHOUR=3;BYMINUTE=30, created DISABLED:
--
--   BEGIN
--     DELETE FROM billing_audit_log WHERE logged_at < SYSDATE - 90;
--     COMMIT;
--   EXCEPTION WHEN OTHERS THEN NULL;
--   END;
--
-- Three things are carried over deliberately:
--
--   * the 90 days are the same 90 days, but they are no longer hardcoded inside the job
--     text: the retention is the `retention_days` job parameter, default 90;
--   * `WHEN OTHERS THEN NULL` is reproduced, not fixed (plan decision P1-D2). The EXIT
--     handler below catches every SQLSTATE and does nothing, so a failed purge is silent
--     and the next run simply tries again - the legacy behaviour an operator relies on
--     today, including the part nobody likes;
--   * `SYSDATE` is the database's wall clock with no zone, so the cutoff is computed from
--     the warehouse's UTC session clock and compared against the zoneless `logged_at`
--     (plan decision P1-D3: UTC assumed and declared, not converted).
--
-- The DELETE is a single atomic statement, so the legacy COMMIT has no counterpart.
-- Re-running the purge is safe: it deletes by age, never by run, so it cannot remove rows
-- a later writer added inside the retention window.

BEGIN
  DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN END;

  DELETE FROM ow_tp.silver.billing_audit_log
   WHERE logged_at < CAST(current_timestamp() AS TIMESTAMP_NTZ)
                     - make_dt_interval(CAST(:retention_days AS INT));
END;
