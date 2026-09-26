-- Reconciliation views read by report-service (§7). Same columns as the Azure SQL views.
CREATE OR REPLACE VIEW mig.v_reconciliation_tables AS
SELECT
    l.run_id,
    l.namespace,
    l.table_name,
    l.table_order,
    l.table_role,
    COALESCE(l.extracted, 0)                                    AS extracted,
    COALESCE(l.loaded, 0)                                       AS loaded,
    COALESCE(l.validated, 0)                                    AS validated,
    COALESCE(l.purged, 0)                                       AS purged,
    COALESCE(l.rejected, 0) + COALESCE(l.validate_failed, 0)    AS failed,
    COALESCE(l.rejected, 0)                                     AS rejected,
    COALESCE(l.validate_failed, 0)                              AS validate_failed,
    COALESCE(l.purge_intended, 0)                               AS purge_intended,
    l.purge_dry_run,
    CASE
        WHEN COALESCE(l.extracted, -1) <> COALESCE(l.loaded, 0) + COALESCE(l.rejected, 0) THEN FALSE
        WHEN COALESCE(l.loaded, -1) <> COALESCE(l.validated, 0) + COALESCE(l.validate_failed, 0) THEN FALSE
        WHEN l.table_role = 'reference' AND COALESCE(l.purged, 0) <> 0 THEN FALSE
        WHEN l.table_role = 'data' AND r.purge_enabled AND COALESCE(l.purged, -1) <> COALESCE(l.validated, 0) THEN FALSE
        WHEN l.table_role = 'data' AND NOT r.purge_enabled
             AND (COALESCE(l.purge_intended, -1) <> COALESCE(l.validated, 0) OR COALESCE(l.purged, 0) <> 0) THEN FALSE
        ELSE TRUE
    END                                                         AS closes
FROM mig.run_ledger AS l
JOIN mig.runs AS r ON r.run_id = l.run_id AND r.namespace = l.namespace;

CREATE OR REPLACE VIEW mig.v_reconciliation_failures AS
SELECT
    j.run_id,
    j.namespace,
    j.table_name,
    j.source_key,
    j.rule_name,
    j.stage,
    j.field,
    j.sqlstate,
    j.native_error,
    j.error,
    j.created_at
FROM mig.rejects AS j;
