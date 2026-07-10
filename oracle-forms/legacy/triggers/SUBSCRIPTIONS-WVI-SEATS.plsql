-- Block:   SUBSCRIPTIONS
-- Item:    SEATS
-- Trigger: WHEN-VALIDATE-ITEM
--
-- Business rule: seats must be at least 1 and may not exceed the plan's
-- MAX_SEATS. The upper bound is plan-dependent (cross-field), so it cannot be
-- expressed by a static field range.

DECLARE
  v_max_seats NUMBER;
BEGIN
  SELECT MAX_SEATS
    INTO v_max_seats
    FROM STORAGE_PLANS
   WHERE PLAN_CODE = :SUBSCRIPTIONS.PLAN_CODE;

  IF :SUBSCRIPTIONS.SEATS IS NULL OR :SUBSCRIPTIONS.SEATS < 1 THEN
    FND_MESSAGE.SET_STRING('Seats must be at least 1');
    FND_MESSAGE.ERROR;
    RAISE FORM_TRIGGER_FAILURE;
  END IF;

  IF :SUBSCRIPTIONS.SEATS > v_max_seats THEN
    FND_MESSAGE.SET_STRING('Seats exceed plan maximum');
    FND_MESSAGE.ERROR;
    RAISE FORM_TRIGGER_FAILURE;
  END IF;
END;
