-- Read-only role for report-service / audit-service (§10). The per-namespace reader login is created by
-- the INIT stage (ensure_reader) and granted this role; it never sees stg.* nor the Db2 source.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ldm_report_reader') THEN
        CREATE ROLE ldm_report_reader NOLOGIN;
    END IF;
END
$$;
GRANT USAGE ON SCHEMA mig TO ldm_report_reader;
GRANT USAGE ON SCHEMA arch TO ldm_report_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mig TO ldm_report_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA arch TO ldm_report_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mig GRANT SELECT ON TABLES TO ldm_report_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA arch GRANT SELECT ON TABLES TO ldm_report_reader;
