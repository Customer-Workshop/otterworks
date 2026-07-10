-- Seed the storage plans (the LOV source and the reference data the cross-field
-- triggers validate seats/discount against). Idempotent and portable across
-- H2 (PostgreSQL mode) and PostgreSQL via INSERT ... WHERE NOT EXISTS.
INSERT INTO storage_plans (plan_code, plan_name, monthly_price, included_gb, max_seats, max_discount_pct)
  SELECT 'FREE', 'Free', 0, 15, 1, 0
  WHERE NOT EXISTS (SELECT 1 FROM storage_plans WHERE plan_code = 'FREE');
INSERT INTO storage_plans (plan_code, plan_name, monthly_price, included_gb, max_seats, max_discount_pct)
  SELECT 'BASIC', 'Basic', 9.99, 100, 5, 0
  WHERE NOT EXISTS (SELECT 1 FROM storage_plans WHERE plan_code = 'BASIC');
INSERT INTO storage_plans (plan_code, plan_name, monthly_price, included_gb, max_seats, max_discount_pct)
  SELECT 'PRO', 'Pro', 29.99, 1000, 25, 0
  WHERE NOT EXISTS (SELECT 1 FROM storage_plans WHERE plan_code = 'PRO');
INSERT INTO storage_plans (plan_code, plan_name, monthly_price, included_gb, max_seats, max_discount_pct)
  SELECT 'ENTERPRISE', 'Enterprise', 99.99, 10000, 500, 20
  WHERE NOT EXISTS (SELECT 1 FROM storage_plans WHERE plan_code = 'ENTERPRISE');
