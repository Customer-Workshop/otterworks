-- Read model for the reconciliation report (CONTRACTS.md §10). The report service reads ONLY these views
-- and mig.runs / mig.run_sessions / mig.class_totals.

CREATE OR ALTER VIEW mig.v_reconciliation_tables AS
SELECT
    l.run_id,
    l.namespace,
    l.table_name,
    l.table_order,
    l.table_role,
    ISNULL(l.extracted, 0)                                  AS extracted,
    ISNULL(l.loaded, 0)                                     AS loaded,
    ISNULL(l.validated, 0)                                  AS validated,
    ISNULL(l.purged, 0)                                     AS purged,
    ISNULL(l.rejected, 0) + ISNULL(l.validate_failed, 0)    AS failed,
    ISNULL(l.rejected, 0)                                   AS rejected,
    ISNULL(l.validate_failed, 0)                            AS validate_failed,
    ISNULL(l.purge_intended, 0)                             AS purge_intended,
    l.purge_dry_run,
    CAST(CASE
        WHEN ISNULL(l.extracted, -1) <> ISNULL(l.loaded, 0) + ISNULL(l.rejected, 0) THEN 0
        WHEN ISNULL(l.loaded, -1) <> ISNULL(l.validated, 0) + ISNULL(l.validate_failed, 0) THEN 0
        WHEN l.table_role = N'reference' AND ISNULL(l.purged, 0) <> 0 THEN 0
        WHEN l.table_role = N'data' AND r.purge_enabled = 1 AND ISNULL(l.purged, -1) <> ISNULL(l.validated, 0) THEN 0
        WHEN l.table_role = N'data' AND r.purge_enabled = 0
             AND (ISNULL(l.purge_intended, -1) <> ISNULL(l.validated, 0) OR ISNULL(l.purged, 0) <> 0) THEN 0
        ELSE 1
    END AS BIT)                                             AS closes
FROM mig.run_ledger AS l
JOIN mig.runs AS r ON r.run_id = l.run_id AND r.namespace = l.namespace;
GO

CREATE OR ALTER VIEW mig.v_reconciliation_failures AS
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
GO
