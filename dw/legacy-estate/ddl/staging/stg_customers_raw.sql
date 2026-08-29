-- Landing table for the CRM nightly extract (source system: SFDC_EXPORT).
-- Loaded by python/load_crm_extract.py via COPY from s3://legacy-dw-landing/crm/.
CREATE TABLE IF NOT EXISTS staging.stg_customers_raw (
    customer_id       BIGINT        NOT NULL ENCODE az64,
    customer_name     VARCHAR(120)  ENCODE lzo,
    email             VARCHAR(160)  ENCODE lzo,
    signup_ts         TIMESTAMP     ENCODE az64,
    country_code      CHAR(2)       ENCODE bytedict,
    city              VARCHAR(80)   ENCODE lzo,
    segment           VARCHAR(20)   ENCODE bytedict,
    marketing_opt_in  BOOLEAN       ENCODE raw,
    source_system     VARCHAR(30)   ENCODE bytedict,
    load_ts           TIMESTAMP     ENCODE az64
)
DISTSTYLE KEY
DISTKEY (customer_id)
COMPOUND SORTKEY (signup_ts, customer_id);
