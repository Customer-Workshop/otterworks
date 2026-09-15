-- U-12 CUSTOMER_MASTER: Oracle OW_BILLING.CUSTOMER_MASTER -> Lakebase ow_tp, schema billing.
-- Unit p1-customer-master (batch w2-b), mapping map-p1-v1, wave branch mig-p1-w2.
--
-- Shape is the source shape: 155 columns, same names, same order. Repeating groups
-- (addr_line_1..6, phone1..4, udf_01..40) and magic-number status codes are left alone;
-- pipeline 1 does not normalize (approved analysis, D8-01).
--
-- Types come from the mapping spec: NUMBER(p,s) money -> numeric(p,s), never float;
-- NUMBER(4) codes -> smallint; NUMBER(12) -> bigint; Oracle DATE -> timestamp(0) because
-- Oracle DATE carries a time part (P1-D3); CHAR(1) Y/N -> char(1); comma-separated id lists
-- stay verbatim text.
--
-- The 15 DD-MON-YY string dates stay varchar(9) and byte-exact, and each gets a `_parsed`
-- timestamp companion with f_str2dt semantics: NULL when the string does not parse, which is
-- the legacy behaviour and part of the declared anomaly set rather than a fix.
--
-- No foreign keys: Oracle enforces none here and the orphan rows have to survive (D8-01).
-- No unique constraint beyond the primary key.
--
-- customer_master_hist and trg_customer_master_hist belong to p1-customer-master-hist
-- (batch w2-d) and are not created here.

CREATE TABLE IF NOT EXISTS billing.customer_master (
    cust_id                 varchar(36) NOT NULL,
    cust_seq_no             bigint,
    tenant_id               varchar(36),
    cust_no                 varchar(20),
    cust_name               varchar(200),
    cust_name_upper         varchar(200),
    legal_name              varchar(200),
    dba_name                varchar(200),
    addr_line_1             varchar(120),
    addr_line_2             varchar(120),
    addr_line_3             varchar(120),
    addr_line_4             varchar(120),
    addr_line_5             varchar(120),
    addr_line_6             varchar(120),
    city                    varchar(80),
    state_cd                varchar(4),
    zip                     varchar(12),
    zip4                    varchar(6),
    country_cd              varchar(4),
    mail_addr_line_1        varchar(120),
    mail_addr_line_2        varchar(120),
    mail_addr_line_3        varchar(120),
    mail_addr_line_4        varchar(120),
    mail_addr_line_5        varchar(120),
    mail_addr_line_6        varchar(120),
    mail_city               varchar(80),
    mail_state_cd           varchar(4),
    mail_zip                varchar(12),
    phone1                  varchar(25),
    phone2                  varchar(25),
    phone3                  varchar(25),
    phone4                  varchar(25),
    phone1_type_cd          smallint,
    phone2_type_cd          smallint,
    phone3_type_cd          smallint,
    phone4_type_cd          smallint,
    fax                     varchar(25),
    email_1                 varchar(200),
    email_2                 varchar(200),
    email_3                 varchar(200),
    signup_dt               varchar(9),
    last_activity_dt        varchar(9),
    last_invoice_dt         varchar(9),
    last_payment_dt         varchar(9),
    terminate_dt            varchar(9),
    status_cd               smallint,
    sub_status_cd           smallint,
    cust_type_cd            smallint,
    segment_cd              smallint,
    region_cd               smallint,
    territory_cd            smallint,
    channel_cd              smallint,
    rate_class_cd           smallint,
    tax_exempt_yn           char(1),
    credit_hold_yn          char(1),
    dunning_exempt_yn       char(1),
    vip_yn                  char(1),
    cur_bal_amt             numeric(14,2),
    past_due_amt            numeric(14,2),
    ytd_billed_amt          numeric(14,2),
    ltd_billed_amt          numeric(14,2),
    ytd_paid_amt            numeric(14,2),
    credit_limit_amt        numeric(14,2),
    related_acct_ids        varchar(2000),
    child_acct_ids          varchar(2000),
    promo_codes_csv         varchar(1000),
    contact_notes           varchar(4000),
    legacy_sys_key          varchar(50),
    mainframe_acct_no       varchar(30),
    conversion_batch_no     integer,
    flag_01                 char(1),
    flag_02                 char(1),
    flag_03                 char(1),
    flag_04                 char(1),
    flag_05                 char(1),
    flag_06                 char(1),
    flag_07                 char(1),
    flag_08                 char(1),
    flag_09                 char(1),
    flag_10                 char(1),
    flag_11                 char(1),
    flag_12                 char(1),
    flag_13                 char(1),
    flag_14                 char(1),
    flag_15                 char(1),
    flag_16                 char(1),
    flag_17                 char(1),
    flag_18                 char(1),
    flag_19                 char(1),
    flag_20                 char(1),
    udf_01                  varchar(100),
    udf_02                  varchar(100),
    udf_03                  varchar(100),
    udf_04                  varchar(100),
    udf_05                  varchar(100),
    udf_06                  varchar(100),
    udf_07                  varchar(100),
    udf_08                  varchar(100),
    udf_09                  varchar(100),
    udf_10                  varchar(100),
    udf_11                  varchar(100),
    udf_12                  varchar(100),
    udf_13                  varchar(100),
    udf_14                  varchar(100),
    udf_15                  varchar(100),
    udf_16                  varchar(100),
    udf_17                  varchar(100),
    udf_18                  varchar(100),
    udf_19                  varchar(100),
    udf_20                  varchar(100),
    udf_21                  varchar(100),
    udf_22                  varchar(100),
    udf_23                  varchar(100),
    udf_24                  varchar(100),
    udf_25                  varchar(100),
    udf_26                  varchar(100),
    udf_27                  varchar(100),
    udf_28                  varchar(100),
    udf_29                  varchar(100),
    udf_30                  varchar(100),
    udf_31                  varchar(100),
    udf_32                  varchar(100),
    udf_33                  varchar(100),
    udf_34                  varchar(100),
    udf_35                  varchar(100),
    udf_36                  varchar(100),
    udf_37                  varchar(100),
    udf_38                  varchar(100),
    udf_39                  varchar(100),
    udf_40                  varchar(100),
    udf_amt_01              numeric(14,2),
    udf_amt_02              numeric(14,2),
    udf_amt_03              numeric(14,2),
    udf_amt_04              numeric(14,2),
    udf_amt_05              numeric(14,2),
    udf_amt_06              numeric(14,2),
    udf_amt_07              numeric(14,2),
    udf_amt_08              numeric(14,2),
    udf_amt_09              numeric(14,2),
    udf_amt_10              numeric(14,2),
    udf_dt_01               varchar(9),
    udf_dt_02               varchar(9),
    udf_dt_03               varchar(9),
    udf_dt_04               varchar(9),
    udf_dt_05               varchar(9),
    udf_dt_06               varchar(9),
    udf_dt_07               varchar(9),
    udf_dt_08               varchar(9),
    udf_dt_09               varchar(9),
    udf_dt_10               varchar(9),
    created_by              varchar(30),
    created_dt              timestamp(0),
    updated_by              varchar(30),
    updated_dt              timestamp(0),
    row_version_no          integer,

    -- f_str2dt companions (P1-D5): the raw varchar(9) column above keeps its
    -- bytes, these carry the parsed value and NULL when the string does not parse.
    signup_dt_parsed        timestamp,
    last_activity_dt_parsed timestamp,
    last_invoice_dt_parsed  timestamp,
    last_payment_dt_parsed  timestamp,
    terminate_dt_parsed     timestamp,
    udf_dt_01_parsed        timestamp,
    udf_dt_02_parsed        timestamp,
    udf_dt_03_parsed        timestamp,
    udf_dt_04_parsed        timestamp,
    udf_dt_05_parsed        timestamp,
    udf_dt_06_parsed        timestamp,
    udf_dt_07_parsed        timestamp,
    udf_dt_08_parsed        timestamp,
    udf_dt_09_parsed        timestamp,
    udf_dt_10_parsed        timestamp,

    CONSTRAINT pk_customer_master PRIMARY KEY (cust_id)
);

-- seq_customer_master: Oracle START WITH 100000 INCREMENT BY 1 NOCACHE; CACHE 1 is the
-- Postgres spelling of NOCACHE. After a backfill the loader moves it past the highest
-- loaded cust_seq_no so application inserts cannot collide with migrated rows.
CREATE SEQUENCE IF NOT EXISTS billing.seq_customer_master
    START WITH 100000 INCREMENT BY 1 NO CYCLE CACHE 1;

-- trg_customer_master_seq: the Oracle BEFORE INSERT ... FOR EACH ROW body as written. It
-- fills the surrogate when the writer left it NULL, sets cust_name_upper from cust_name, and
-- defaults row_version_no to 1. Oracle fires it on INSERT only, so an UPDATE that changes
-- cust_name leaves cust_name_upper stale; that asymmetry is source behaviour and is
-- reproduced, not fixed.
CREATE OR REPLACE FUNCTION billing.trg_customer_master_seq() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.cust_seq_no IS NULL THEN
        NEW.cust_seq_no := nextval('billing.seq_customer_master');
    END IF;
    NEW.cust_name_upper := upper(NEW.cust_name);
    NEW.row_version_no := coalesce(NEW.row_version_no, 1);
    RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS trg_customer_master_seq ON billing.customer_master;
CREATE TRIGGER trg_customer_master_seq
    BEFORE INSERT ON billing.customer_master
    FOR EACH ROW EXECUTE FUNCTION billing.trg_customer_master_seq();
