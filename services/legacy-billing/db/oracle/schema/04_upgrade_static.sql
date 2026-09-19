-- Idempotent static-data upgrades applied on every Oracle billing boot.
WHENEVER SQLERROR EXIT SQL.SQLCODE
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

DECLARE
    marker_columns NUMBER;
BEGIN
    SELECT COUNT(*) INTO marker_columns
      FROM user_tab_columns
     WHERE table_name = 'FIXTURE_META'
       AND column_name = 'MARKER';
    IF marker_columns = 0 THEN
        EXECUTE IMMEDIATE
            'ALTER TABLE fixture_meta ADD (marker VARCHAR2(100), value VARCHAR2(100))';
    END IF;
END;
/

INSERT INTO tenants (id, name, tax_exempt_yn, status_cd)
SELECT 'a0000000-0000-0000-0000-000000000001', 'OtterWorks Admin', 'N', 10
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM tenants
        WHERE id = 'a0000000-0000-0000-0000-000000000001'
 );

INSERT INTO subscriptions
    (id, tenant_id, plan_id, starts_on, ends_on, status_cd, suspended_on)
SELECT '20000000-0000-0000-0000-00000000a001',
       'a0000000-0000-0000-0000-000000000001',
       '10000000-0000-0000-0000-000000000002',
       DATE '2026-01-01', NULL, 10, NULL
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM subscriptions
        WHERE id = '20000000-0000-0000-0000-00000000a001'
 );

INSERT INTO usage_events (id, tenant_id, occurred_at, units, kind_cd)
SELECT '30000000-0000-0000-0000-00000000a001',
       'a0000000-0000-0000-0000-000000000001',
       TIMESTAMP '2026-02-10 10:00:00', 260, 1
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM usage_events
        WHERE id = '30000000-0000-0000-0000-00000000a001'
 );
INSERT INTO usage_events (id, tenant_id, occurred_at, units, kind_cd)
SELECT '30000000-0000-0000-0000-00000000a002',
       'a0000000-0000-0000-0000-000000000001',
       TIMESTAMP '2026-02-15 10:00:00', 700, 2
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM usage_events
        WHERE id = '30000000-0000-0000-0000-00000000a002'
 );
INSERT INTO usage_events (id, tenant_id, occurred_at, units, kind_cd)
SELECT '30000000-0000-0000-0000-00000000a003',
       'a0000000-0000-0000-0000-000000000001',
       TIMESTAMP '2026-02-20 10:00:00', 2201, 3
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM usage_events
        WHERE id = '30000000-0000-0000-0000-00000000a003'
 );

INSERT INTO invoices
    (id, tenant_id, period_id, issued_at, subtotal, tax, total, status_cd)
SELECT '60000000-0000-0000-0000-000000000009',
       'a0000000-0000-0000-0000-000000000001',
       '40000000-0000-0000-0000-000000000001',
       TIMESTAMP '2026-02-01 00:00:00', 149.00, 12.29, 161.29, 30
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM invoices
        WHERE id = '60000000-0000-0000-0000-000000000009'
 );

INSERT INTO invoice_lines
    (id, invoice_id, line_no, line_type, description, amount)
SELECT 'a0000000-0000-0000-0000-000000000009',
       '60000000-0000-0000-0000-000000000009',
       1, 'plan', 'GROWTH', 149.00
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM invoice_lines
        WHERE id = 'a0000000-0000-0000-0000-000000000009'
 );
INSERT INTO invoice_lines
    (id, invoice_id, line_no, line_type, description, amount)
SELECT 'a0000000-0000-0000-0000-00000000000a',
       '60000000-0000-0000-0000-000000000009',
       2, 'usage', 'usage overage', 12.29
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM invoice_lines
        WHERE id = 'a0000000-0000-0000-0000-00000000000a'
 );

INSERT INTO customer_master (
    cust_id, tenant_id, cust_no, cust_name, legal_name,
    addr_line_1, city, state_cd, zip, country_cd,
    phone1, phone1_type_cd, email_1, signup_dt, last_activity_dt,
    status_cd, sub_status_cd, cust_type_cd, segment_cd, region_cd,
    tax_exempt_yn, credit_hold_yn, dunning_exempt_yn, vip_yn,
    cur_bal_amt, past_due_amt, ytd_billed_amt, ltd_billed_amt,
    ytd_paid_amt, credit_limit_amt, conversion_batch_no, created_by,
    created_dt, updated_by, updated_dt
)
SELECT
    '40000000-0000-0000-0000-00000000a001',
    'a0000000-0000-0000-0000-000000000001',
    'OW-ADMIN-0001', 'OtterWorks Admin', 'OtterWorks Admin',
    '1 OtterWorks Way', 'Springfield', 'IL', '62701', 'US',
    '217-555-0100', 1, 'admin@otterworks.dev',
    '01-JAN-26', '20-FEB-26',
    1, 1, 1, 1, 1,
    'N', 'N', 'N', 'Y',
    149.00, 0.00, 149.00, 149.00,
    149.00, 5000.00, NULL, 'SEED',
    DATE '2026-01-01', 'SEED', DATE '2026-02-20'
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM customer_master
        WHERE cust_id = '40000000-0000-0000-0000-00000000a001'
 );

INSERT INTO entity_attr_value
    (eav_id, entity_type, entity_id, attr_name, attr_value, attr_type, created_dt)
SELECT 99000000000001, 'CUSTOMER',
       '40000000-0000-0000-0000-00000000a001',
       'TAX_REGION_OVERRIDE', 'US-IL', 'STR', '20-FEB-26'
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM entity_attr_value
        WHERE eav_id = 99000000000001
 );
INSERT INTO entity_attr_value
    (eav_id, entity_type, entity_id, attr_name, attr_value, attr_type, created_dt)
SELECT 99000000000002, 'CUSTOMER',
       '40000000-0000-0000-0000-00000000a001',
       'tax_region_override', 'us-il', 'STR', '20-FEB-26'
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM entity_attr_value
        WHERE eav_id = 99000000000002
 );
INSERT INTO entity_attr_value
    (eav_id, entity_type, entity_id, attr_name, attr_value, attr_type, created_dt)
SELECT 99000000000003, 'CUSTOMER',
       '40000000-0000-0000-0000-00000000a001',
       'PORTAL_THEME', 'dark', 'STR', '20-FEB-26'
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM entity_attr_value
        WHERE eav_id = 99000000000003
 );
INSERT INTO entity_attr_value
    (eav_id, entity_type, entity_id, attr_name, attr_value, attr_type, created_dt)
SELECT 99000000000004, 'CUSTOMER',
       '40000000-0000-0000-0000-00000000a001',
       'LEGACY_TIER', 'priority', 'STR', '20-FEB-26'
  FROM dual
 WHERE NOT EXISTS (
       SELECT 1 FROM entity_attr_value
        WHERE eav_id = 99000000000004
 );

MERGE INTO fixture_meta target
USING (SELECT 'static_seed_version' AS marker, '2' AS value FROM dual) source
   ON (target.marker = source.marker)
 WHEN MATCHED THEN
      UPDATE SET target.value = source.value
 WHEN NOT MATCHED THEN
      INSERT (marker, value, initialized_at)
      VALUES (source.marker, source.value, SYSTIMESTAMP);

COMMIT;
EXIT;
