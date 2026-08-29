-- Audit trail for the order dedupe step. Written for the 2019 data-quality
-- review; the dashboard that read it was retired and the step was folded into
-- sp_load_orders_incremental, so nothing schedules this any more.

INSERT INTO core.stg_orders_dedup_audit
    (audit_id, run_ts, source_rows, retained_rows, duplicate_rows)
SELECT DATEDIFF(second, '2000-01-01'::TIMESTAMP, GETDATE()),
       GETDATE(),
       COUNT(*),
       COUNT(DISTINCT order_id),
       COUNT(*) - COUNT(DISTINCT order_id)
FROM staging.stg_orders_raw
WHERE order_ts >= DATEADD(day, -1, GETDATE());
