-- Block:   SUBSCRIPTIONS
-- Trigger: PRE-INSERT
--
-- Business rule: a subscription may not be created for a customer whose status
-- is CLOSED. Enforced at insert time against the parent CUSTOMERS record.

DECLARE
  v_cust_status VARCHAR2(10);
BEGIN
  SELECT STATUS
    INTO v_cust_status
    FROM BILLING_CUSTOMERS
   WHERE CUSTOMER_ID = :SUBSCRIPTIONS.CUSTOMER_ID;

  IF v_cust_status = 'CLOSED' THEN
    FND_MESSAGE.SET_STRING('Cannot add subscription for a closed customer');
    FND_MESSAGE.ERROR;
    RAISE FORM_TRIGGER_FAILURE;
  END IF;
END;
