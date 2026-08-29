-- Customer history dimension maintained by core.sp_merge_customer_scd2.
CREATE SEQUENCE IF NOT EXISTS core.dim_customer_scd2_sk_seq;

CREATE TABLE IF NOT EXISTS core.dim_customer_scd2 (
    customer_sk      BIGINT        NOT NULL ENCODE az64,
    customer_id      BIGINT        NOT NULL ENCODE az64,
    customer_name    VARCHAR(120)  ENCODE lzo,
    email            VARCHAR(160)  ENCODE lzo,
    country_code     CHAR(2)       ENCODE bytedict,
    city             VARCHAR(80)   ENCODE lzo,
    segment          VARCHAR(20)   ENCODE bytedict,
    marketing_opt_in BOOLEAN       ENCODE raw,
    hash_diff        VARCHAR(32)   ENCODE lzo,
    effective_from   TIMESTAMP     ENCODE az64,
    effective_to     TIMESTAMP     ENCODE az64,
    is_current       BOOLEAN       ENCODE raw,
    PRIMARY KEY (customer_sk)
)
DISTSTYLE KEY
DISTKEY (customer_id)
COMPOUND SORTKEY (customer_id, effective_from);
