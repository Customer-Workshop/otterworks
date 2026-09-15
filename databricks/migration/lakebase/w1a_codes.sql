-- U-11 CODES -> Lakebase billing.codes (unit p1-codes, wave 1 batch a).
--
-- Oracle source: OW_BILLING.CODES (services/legacy-billing/db/oracle/schema/01_tables.sql).
-- This is the generic magic-number lookup every *_CD column joins to by convention. Nothing
-- enforces the convention in Oracle and nothing enforces it here: no foreign keys are added
-- to the referring tables, because adding them would reject legacy rows whose code has no
-- lookup row (D8-01: orphans are reproduced, not cleaned).
--
-- The composite primary key (CODE_TYPE, CODE_VAL) keeps its Oracle name and column order, so
-- the index it creates still serves the equality lookup that billing.f_code_desc(text,
-- numeric) - already deployed in wave 0 - runs on every read. CODE_VAL stays a small integer
-- (NUMBER(4) -> smallint); the function's numeric parameter compares to it without a cast
-- that would defeat the index.

CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE IF NOT EXISTS billing.codes (
    code_type varchar(30) NOT NULL,
    code_val  smallint    NOT NULL,
    code_desc varchar(80) NOT NULL,
    CONSTRAINT pk_codes PRIMARY KEY (code_type, code_val)
);

COMMENT ON TABLE billing.codes IS
    'Migration unit p1-codes (U-11) from Oracle OW_BILLING.CODES; read by billing.f_code_desc.';
