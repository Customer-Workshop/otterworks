-- COMMISSION_DW.DIM_PRODUCT -> ow_tp.silver.dim_product_cdw
-- Source DDL: services/industry-solutions/insurance/db/olap/01_star_schema.sql (dim_product).
-- product_key is the legacy identity value carried over verbatim (DEC-003); never GENERATED.
-- Idempotent: every run drops and recreates the unit's own table (no other object is touched).
DROP TABLE IF EXISTS ow_tp.silver.dim_product_cdw;

CREATE TABLE ow_tp.silver.dim_product_cdw (
    product_key      BIGINT    NOT NULL COMMENT 'legacy DIM_PRODUCT.PRODUCT_KEY (NUMBER identity), carried over',
    product_code     STRING    NOT NULL COMMENT 'natural key, legacy VARCHAR2(16) UNIQUE',
    product_name     STRING    NOT NULL COMMENT 'legacy VARCHAR2(120)',
    line_of_business STRING    NOT NULL COMMENT 'legacy VARCHAR2(24)',
    loaded_at        TIMESTAMP NOT NULL COMMENT 'server-side load time, excluded from recon'
)
USING DELTA
COMMENT 'Commission Pay product dimension (COMMISSION_DW.DIM_PRODUCT), namespace cdw';
