-- Read-only role for the Report and Audit services. 'ldm init' creates the contained user named by
-- AZSQL_READER_USER (password from AZSQL_READER_PASSWORD) and adds it to this role; no password lives here.

IF DATABASE_PRINCIPAL_ID(N'ldm_report_reader') IS NULL
CREATE ROLE ldm_report_reader;
GO
GRANT SELECT ON SCHEMA::mig TO ldm_report_reader;
GO
GRANT SELECT ON SCHEMA::arch TO ldm_report_reader;
GO
