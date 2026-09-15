-- Wave 0, batch w0-a: pkg_ow_util converted to PL/pgSQL, plus the wave-0 scaffolding the
-- later waves code against.
--
-- Source: services/legacy-billing/db/oracle/packages/01_pkg_util.sql (read-only).
-- Target: Lakebase project ow-tp-billing, database ow_tp, schema billing, on the wave branch.
-- Idempotent: every statement is CREATE ... IF NOT EXISTS or CREATE OR REPLACE (P1-D6).
--
-- Package state (g_call_count, g_last_module, g_last_uuid) is NOT reproduced as hidden
-- session state. Oracle's globals here are write-only bookkeeping: no caller reads them
-- (verified across the four packages), so they become the audit-log row that log_msg already
-- writes rather than a table nobody queries. The state that IS read across packages -
-- pkg_rating's g_overage_amount - becomes billing.rating_state below (P1-D4).

CREATE SCHEMA IF NOT EXISTS billing;

-- f_md5_uuid: MD5 of the UTF-8 bytes, lowercase hex, hyphenated 8-4-4-4-12. Oracle's
-- STANDARD_HASH(UTL_RAW.CAST_TO_RAW(x),'MD5') hashes the raw bytes of the string, which is
-- what Postgres md5(text) does on a UTF-8 database. NULL in, NULL out (Oracle returns NULL
-- because SUBSTR of NULL is NULL); empty string is NOT null here, unlike Oracle, so it is in
-- the parity vector explicitly - see the D2-01 note in the unit's summary.
CREATE OR REPLACE FUNCTION billing.f_md5_uuid(p_input text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE WHEN p_input IS NULL THEN NULL ELSE
        substr(md5(p_input), 1, 8)  || '-' ||
        substr(md5(p_input), 9, 4)  || '-' ||
        substr(md5(p_input), 13, 4) || '-' ||
        substr(md5(p_input), 17, 4) || '-' ||
        substr(md5(p_input), 21, 12)
    END
$$;

-- f_code_desc: the Oracle version wraps a static lookup in EXECUTE IMMEDIATE. Converted to a
-- plain query. NO_DATA_FOUND -> 'UNKNOWN(<val>)' with NVL(p_val,-1), reproduced exactly,
-- including the -1 for a NULL code value.
CREATE OR REPLACE FUNCTION billing.f_code_desc(p_type text, p_val numeric)
RETURNS text
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_desc text;
BEGIN
    SELECT code_desc INTO v_desc
      FROM billing.codes
     WHERE code_type = p_type AND code_val = p_val;
    IF NOT FOUND THEN
        RETURN 'UNKNOWN(' || COALESCE(p_val, -1)::text || ')';
    END IF;
    RETURN v_desc;
END;
$$;

-- f_dt2str: 'DD-MON-YY' with English month abbreviations, upper case, as Oracle's
-- TO_CHAR under NLS_DATE_LANGUAGE=ENGLISH gives. The day is zero-padded to two digits
-- ('03-JAN-24'), so no FM: FM would strip the leading zero and diverge on days 1-9.
CREATE OR REPLACE FUNCTION billing.f_dt2str(p_dt date)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE WHEN p_dt IS NULL THEN NULL
                ELSE to_char(p_dt, 'DD-MON-YY') END
$$;

-- f_str2dt: returns NULL on anything unparseable, silently. That is contract, not a bug
-- (P1-D2): the malformed dates are a declared anomaly set and the report surfaces depend on
-- the NULL.
--
-- Postgres to_date does not behave like Oracle TO_DATE here, so the string is taken apart
-- explicitly instead. Each difference below is one measured by
-- databricks/migration/lakebase/w0a_date_parity.py against the live source:
--   * to_date is permissive where Oracle raises: '32-JAN-24' rolls into February and
--     '31-FEB-24' into March. make_date rejects both, so the anomaly set keeps its NULLs.
--   * the 'YY' pivot differs. Oracle's YY always means the current century ('15-MAR-99' is
--     2099); Postgres reads 70-99 as 19xx. Two-digit years are therefore 2000 + yy.
--   * Oracle accepts an unpadded day, a four-digit year and any punctuation as separator
--     ('1-JAN-24', '15-MAR-1999', '15/MAR/99' all parse). The regex allows the same shapes.
--   * month names are locale-sensitive in Postgres; the month is matched against a fixed
--     English list, which is what NLS_DATE_LANGUAGE=ENGLISH gives on the source.
CREATE OR REPLACE FUNCTION billing.f_str2dt(p_str text)
RETURNS date
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_parts text[];
    v_mon   int;
    v_year  int;
BEGIN
    v_parts := regexp_match(upper(btrim(p_str)),
                            '^([0-9]{1,2})[^0-9A-Z]+([A-Z]{3})[A-Z]*[^0-9A-Z]+([0-9]{1,4})$');
    IF v_parts IS NULL THEN
        RETURN NULL;
    END IF;
    v_mon := array_position(
        ARRAY['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'],
        v_parts[2]);
    IF v_mon IS NULL THEN
        RETURN NULL;
    END IF;
    v_year := v_parts[3]::int;
    IF length(v_parts[3]) <= 2 THEN
        v_year := 2000 + v_year;  -- Oracle 'YY': current century, not Postgres's pivot
    END IF;
    RETURN make_date(v_year, v_mon, v_parts[1]::int);
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;  -- impossible day, as Oracle's ORA-01839/ORA-01847 path returns
END;
$$;

-- billing_audit_log: written by log_msg's autonomous transaction. This unit owns the
-- operational copy; ow_tp.silver.billing_audit_log (U-19) is the analytical copy.
-- Column names and order follow OW_BILLING.BILLING_AUDIT_LOG (01_tables.sql:169): the
-- mappings and the analytical copy both address logged_at. Oracle's DATE carries whole
-- seconds and no zone, so timestamp(0) truncated to the second, not timestamptz.
CREATE TABLE IF NOT EXISTS billing.billing_audit_log (
    log_id    bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    logged_at timestamp(0) NOT NULL DEFAULT date_trunc('second', localtimestamp),
    module    varchar(30),
    message   varchar(4000)
);

-- Earlier wave-0 runs of this script created the column as created_at timestamptz. The
-- branch is a migration branch and the table is write-empty until wave 3, so bring an
-- already-created table onto the source's name and type in place.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'billing' AND table_name = 'billing_audit_log'
                 AND column_name = 'created_at') THEN
        ALTER TABLE billing.billing_audit_log RENAME COLUMN created_at TO logged_at;
    END IF;
    ALTER TABLE billing.billing_audit_log
        ALTER COLUMN logged_at TYPE timestamp(0),
        ALTER COLUMN logged_at SET DEFAULT date_trunc('second', localtimestamp);
END;
$$;

-- log_msg: Oracle's PRAGMA AUTONOMOUS_TRANSACTION commits the log row even when the caller
-- rolls back, and swallows its own failures (P1-D1). The swallow is reproduced here. The
-- commit-independence is NOT, and cannot be from inside the database on this platform:
-- Postgres has no autonomous transaction, and a second connection needs dblink, which this
-- Lakebase project refuses ("extension "dblink" is not in the allowed extensions list",
-- probed by databricks/migration/lakebase/probe_dblink.py; pg_available_extensions is empty
-- for dblink and postgres_fdw). So a caller that rolls back loses its log rows, where Oracle
-- keeps them.
--
-- This is a declared behaviour divergence (P1-D1a), open for the user at STOP E, not a
-- solved item: closing it needs an out-of-database writer (the D4-02 shim service holding a
-- second connection, or an async sink), which is application work with its own owner.
CREATE OR REPLACE FUNCTION billing.log_msg(p_module text, p_message text)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO billing.billing_audit_log (module, message)
    VALUES (left(p_module, 30), left(p_message, 4000));
EXCEPTION
    WHEN OTHERS THEN
        NULL;  -- swallowed, exactly as Oracle does
END;
$$;

-- rating_state: the explicit pkg_rating -> pkg_invoicing hand-off that replaces Oracle's
-- mutable package global g_overage_amount (P1-D4). Wave 3 codes against this shape: w3-a
-- writes it, w3-b reads it, concurrently.
CREATE TABLE IF NOT EXISTS billing.rating_state (
    tenant_id      text        NOT NULL,
    period_id      text        NOT NULL,
    overage_amount numeric(18, 2),
    finalized      boolean     NOT NULL DEFAULT false,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, period_id)
);

-- md5_parity_input: the seed table the three MD5 parity ops compare against. Seeded over the
-- read-only JDBC path with the exact inputs Oracle used for the ids it already stores.
CREATE TABLE IF NOT EXISTS billing.md5_parity_input (
    vector text NOT NULL,
    input  text,
    PRIMARY KEY (vector, input)
);
