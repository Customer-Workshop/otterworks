-- Block:   SUBSCRIPTIONS
-- Item:    DISCOUNT_PCT
-- Trigger: WHEN-VALIDATE-ITEM
--
-- Business rule: a subscription's discount may not exceed the maximum discount
-- allowed by its plan. Non-enterprise plans carry MAX_DISCOUNT_PCT = 0, so in
-- practice discounts are ENTERPRISE-only. The per-field format mask already
-- constrains the value to 0..100; THIS trigger adds the plan-dependent
-- (cross-field) cap that a field-level check alone cannot express.

DECLARE
  v_max_discount NUMBER;
BEGIN
  SELECT MAX_DISCOUNT_PCT
    INTO v_max_discount
    FROM STORAGE_PLANS
   WHERE PLAN_CODE = :SUBSCRIPTIONS.PLAN_CODE;

  IF NVL(:SUBSCRIPTIONS.DISCOUNT_PCT, 0) > v_max_discount THEN
    FND_MESSAGE.SET_STRING('Discount exceeds plan maximum');
    FND_MESSAGE.ERROR;
    RAISE FORM_TRIGGER_FAILURE;
  END IF;
END;
