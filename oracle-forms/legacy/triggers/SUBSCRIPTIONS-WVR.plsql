-- Block:   SUBSCRIPTIONS
-- Trigger: WHEN-VALIDATE-RECORD
--
-- Business rule: if an end date is supplied it must be strictly after the
-- start date. A record-level trigger is used because the rule spans two items.

BEGIN
  IF :SUBSCRIPTIONS.END_DATE IS NOT NULL
     AND :SUBSCRIPTIONS.END_DATE <= :SUBSCRIPTIONS.START_DATE THEN
    FND_MESSAGE.SET_STRING('End date must be after start date');
    FND_MESSAGE.ERROR;
    RAISE FORM_TRIGGER_FAILURE;
  END IF;
END;
