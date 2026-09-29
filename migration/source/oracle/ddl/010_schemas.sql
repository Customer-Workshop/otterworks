-- Oracle Database 23ai Free (Exadata / RAC stand-in). Runs as SYS in the CDB from
-- /container-entrypoint-initdb.d on the FIRST start of the container only (gvenzl/oracle-free).
-- Every script switches into the application PDB first: the archive estate lives in FREEPDB1.
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER SESSION SET CONTAINER = FREEPDB1;

-- Schema owners are pure containers: no password, nobody can log in as them.
CREATE USER ARCHIVE NO AUTHENTICATION DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS;
CREATE USER MIGAUDIT NO AUTHENTICATION DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS;
