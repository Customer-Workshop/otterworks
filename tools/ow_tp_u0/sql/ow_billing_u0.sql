DROP SCHEMA IF EXISTS ow_billing CASCADE;
DROP SCHEMA IF EXISTS util CASCADE;
DROP SCHEMA IF EXISTS plans CASCADE;
DROP SCHEMA IF EXISTS usage CASCADE;
DROP SCHEMA IF EXISTS rating CASCADE;
DROP SCHEMA IF EXISTS invoicing CASCADE;

CREATE SCHEMA ow_billing;
CREATE SCHEMA util;
CREATE SCHEMA plans;
CREATE SCHEMA usage;
CREATE SCHEMA rating;
CREATE SCHEMA invoicing;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ow_billing_app') THEN
        CREATE ROLE ow_billing_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ow_billing_ro') THEN
        CREATE ROLE ow_billing_ro NOLOGIN;
    END IF;
END
$$;

ALTER SCHEMA ow_billing OWNER TO ow_billing_app;
ALTER SCHEMA util OWNER TO ow_billing_app;
ALTER SCHEMA plans OWNER TO ow_billing_app;
ALTER SCHEMA usage OWNER TO ow_billing_app;
ALTER SCHEMA rating OWNER TO ow_billing_app;
ALTER SCHEMA invoicing OWNER TO ow_billing_app;

CREATE TABLE ow_billing.codes (
    code_type varchar(30) NOT NULL,
    code_val smallint NOT NULL,
    code_desc varchar(80) NOT NULL,
    CONSTRAINT pk_codes PRIMARY KEY (code_type, code_val)
);

CREATE TABLE ow_billing.tenants (
    id varchar(36) NOT NULL,
    name varchar(200) NOT NULL,
    tax_exempt_yn char(1) NOT NULL DEFAULT 'N',
    status_cd smallint NOT NULL,
    CONSTRAINT pk_tenants PRIMARY KEY (id),
    CONSTRAINT uq_tenants_name UNIQUE (name)
);

CREATE TABLE ow_billing.plans (
    id varchar(36) NOT NULL,
    code varchar(50) NOT NULL,
    tier_cd smallint NOT NULL,
    monthly_fee numeric(12,2) NOT NULL,
    included_units bigint NOT NULL,
    overage_rate numeric(12,6) NOT NULL,
    active_yn char(1) NOT NULL DEFAULT 'Y',
    CONSTRAINT pk_plans PRIMARY KEY (id),
    CONSTRAINT uq_plans_code UNIQUE (code)
);

CREATE TABLE ow_billing.billing_audit_log (
    log_id bigint NOT NULL,
    logged_at timestamp(0) NOT NULL DEFAULT localtimestamp,
    module varchar(30),
    message varchar(4000),
    CONSTRAINT pk_billing_audit_log PRIMARY KEY (log_id)
);

CREATE SEQUENCE ow_billing.seq_billing_audit_log
    START 1 INCREMENT 1 CACHE 1;

CREATE OR REPLACE FUNCTION ow_billing.billing_audit_log_id()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.log_id IS NULL THEN
        NEW.log_id := nextval('ow_billing.seq_billing_audit_log');
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER trg_billing_audit_log_id
BEFORE INSERT ON ow_billing.billing_audit_log
FOR EACH ROW
EXECUTE FUNCTION ow_billing.billing_audit_log_id();

ALTER TABLE ow_billing.codes REPLICA IDENTITY FULL;
ALTER TABLE ow_billing.plans REPLICA IDENTITY FULL;
ALTER TABLE ow_billing.tenants REPLICA IDENTITY FULL;
ALTER TABLE ow_billing.billing_audit_log REPLICA IDENTITY FULL;

CREATE OR REPLACE FUNCTION util.f_md5_uuid(p_input text)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_hex text;
BEGIN
    IF p_input IS NULL THEN
        RETURN NULL;
    END IF;
    v_hex := lower(md5(p_input));
    RETURN substr(v_hex, 1, 8) || '-' ||
           substr(v_hex, 9, 4) || '-' ||
           substr(v_hex, 13, 4) || '-' ||
           substr(v_hex, 17, 4) || '-' ||
           substr(v_hex, 21, 12);
END
$$;

CREATE OR REPLACE FUNCTION util.f_code_desc(p_type text, p_val numeric)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    v_desc text;
BEGIN
    SELECT code_desc
      INTO v_desc
      FROM ow_billing.codes
     WHERE code_type = p_type
       AND code_val = p_val;
    IF NOT FOUND THEN
        RETURN 'UNKNOWN(' || trim_scale(coalesce(p_val, -1))::text || ')';
    END IF;
    RETURN v_desc;
END
$$;

CREATE OR REPLACE FUNCTION util.f_dt2str(p_dt timestamp)
RETURNS text
LANGUAGE sql
AS $$
    SELECT to_char(p_dt, 'DD-MON-YY')
$$;

CREATE OR REPLACE FUNCTION util.f_str2dt(p_str text)
RETURNS timestamp(0)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN to_timestamp(p_str, 'DD-MON-YY')::timestamp(0);
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END
$$;

CREATE OR REPLACE PROCEDURE util.log_msg(p_module text, p_message text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO ow_billing.billing_audit_log (module, message)
    VALUES (substr(p_module, 1, 30), substr(p_message, 1, 4000));
END
$$;

CREATE OR REPLACE PROCEDURE util.purge_audit_log(p_retention_days integer DEFAULT 90)
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM ow_billing.billing_audit_log
     WHERE logged_at < localtimestamp - make_interval(days => p_retention_days);
END
$$;

GRANT USAGE ON SCHEMA ow_billing, util, plans, usage, rating, invoicing
    TO ow_billing_ro, ow_billing_app;
GRANT SELECT ON ALL TABLES IN SCHEMA ow_billing TO ow_billing_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA ow_billing
    GRANT SELECT ON TABLES TO ow_billing_ro;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA util TO ow_billing_ro, ow_billing_app;
GRANT EXECUTE ON ALL PROCEDURES IN SCHEMA util TO ow_billing_ro, ow_billing_app;
