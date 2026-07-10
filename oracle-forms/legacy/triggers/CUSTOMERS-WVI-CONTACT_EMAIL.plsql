-- Block:   CUSTOMERS
-- Item:    CONTACT_EMAIL
-- Trigger: WHEN-VALIDATE-ITEM
--
-- Business rule: the contact email is required and must look like an email
-- address (contain an '@' and a '.' in the domain part). Max length 120.

DECLARE
  v_email VARCHAR2(120) := :CUSTOMERS.CONTACT_EMAIL;
BEGIN
  IF v_email IS NULL
     OR INSTR(v_email, '@') = 0
     OR INSTR(v_email, '.', INSTR(v_email, '@')) = 0 THEN
    FND_MESSAGE.SET_STRING('Contact email must be a valid email address');
    FND_MESSAGE.ERROR;
    RAISE FORM_TRIGGER_FAILURE;
  END IF;
END;
