"""Contract-parity tests for the modernized OtterWorks Storage Billing API.

Each test cites the Forms artifact (block / item / trigger) whose behavior it
proves the REST service reproduces. Source of truth:
  - oracle-forms/contracts/openapi.yaml
  - oracle-forms/legacy/BILLING.fmb.xml  (+ legacy/triggers/*.plsql)
"""

import datetime as dt

import requests

TODAY = dt.date.today().isoformat()
LATER = (dt.date.today() + dt.timedelta(days=30)).isoformat()


# --------------------------------------------------------------------------- #
# Endpoint existence + reference data (LOV source)                            #
# --------------------------------------------------------------------------- #
def test_health(base_url):
    r = requests.get(f"{base_url}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_list_plans_matches_lov(base_url):
    """RecordGroup PLAN_RG / LOV PLAN_LOV -> GET /api/plans returns the four plans."""
    r = requests.get(f"{base_url}/api/plans", timeout=5)
    assert r.status_code == 200
    plans = {p["planCode"]: p for p in r.json()}
    assert set(plans) == {"FREE", "BASIC", "PRO", "ENTERPRISE"}
    # Plan-dependent caps the cross-field triggers validate against:
    assert plans["ENTERPRISE"]["maxDiscountPct"] == 20
    assert plans["PRO"]["maxDiscountPct"] == 0
    assert plans["BASIC"]["maxSeats"] == 5


def test_get_unknown_plan_404(base_url):
    r = requests.get(f"{base_url}/api/plans/GOLD", timeout=5)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# CUSTOMERS block: item + trigger parity                                      #
# --------------------------------------------------------------------------- #
def test_create_customer_ok(base_url):
    r = requests.post(
        f"{base_url}/api/customers",
        json={"companyName": "Acme Corp", "contactEmail": "ops@acme.example"},
        timeout=5,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["customerId"] is not None
    assert body["status"] == "ACTIVE"  # CUSTOMERS.STATUS Initial_Value


def test_create_customer_missing_email_400(base_url):
    """CUSTOMERS.CONTACT_EMAIL Required=true."""
    r = requests.post(
        f"{base_url}/api/customers", json={"companyName": "Acme"}, timeout=5
    )
    assert r.status_code == 400
    assert r.json()["field"] == "contactEmail"


def test_create_customer_bad_email_400(base_url):
    """CUSTOMERS.CONTACT_EMAIL WHEN-VALIDATE-ITEM: must be email-shaped."""
    r = requests.post(
        f"{base_url}/api/customers",
        json={"companyName": "Acme", "contactEmail": "not-an-email"},
        timeout=5,
    )
    assert r.status_code == 400
    assert r.json()["field"] == "contactEmail"


def test_create_customer_bad_status_400(base_url):
    """CUSTOMERS.STATUS LOV STATUS_LOV: ACTIVE|SUSPENDED|CLOSED only."""
    r = requests.post(
        f"{base_url}/api/customers",
        json={"companyName": "Acme", "contactEmail": "a@b.co", "status": "PENDING"},
        timeout=5,
    )
    assert r.status_code == 400
    assert r.json()["field"] == "status"


# --------------------------------------------------------------------------- #
# SUBSCRIPTIONS block: trigger parity                                          #
# --------------------------------------------------------------------------- #
def _sub(base_url, customer_id, **overrides):
    body = {"planCode": "PRO", "seats": 1, "discountPct": 0, "startDate": TODAY}
    body.update(overrides)
    return requests.post(
        f"{base_url}/api/customers/{customer_id}/subscriptions", json=body, timeout=5
    )


def test_subscription_valid_201_and_persisted(base_url, make_customer):
    cid = make_customer()
    r = _sub(base_url, cid, planCode="PRO", seats=10)
    assert r.status_code == 201, r.text
    listed = requests.get(
        f"{base_url}/api/customers/{cid}/subscriptions", timeout=5
    ).json()
    assert any(s["planCode"] == "PRO" and s["seats"] == 10 for s in listed)


def test_subscription_unknown_plan_400(base_url, make_customer):
    """SUBSCRIPTIONS.PLAN_CODE LOV PLAN_LOV / Validate_from_List."""
    cid = make_customer()
    r = _sub(base_url, cid, planCode="GOLD")
    assert r.status_code == 400
    assert r.json()["field"] == "planCode"


def test_subscription_seats_below_one_400(base_url, make_customer):
    """SUBSCRIPTIONS.SEATS WHEN-VALIDATE-ITEM: seats >= 1."""
    cid = make_customer()
    r = _sub(base_url, cid, planCode="PRO", seats=0)
    assert r.status_code == 400
    assert r.json()["field"] == "seats"


def test_subscription_seats_over_plan_max_400(base_url, make_customer):
    """SUBSCRIPTIONS.SEATS WHEN-VALIDATE-ITEM: seats <= plan.maxSeats (cross-field)."""
    cid = make_customer()
    r = _sub(base_url, cid, planCode="BASIC", seats=10)  # BASIC max_seats = 5
    assert r.status_code == 400
    assert r.json()["field"] == "seats"
    assert "maximum" in r.json()["message"].lower()


def test_subscription_discount_ok_on_enterprise_201(base_url, make_customer):
    """ENTERPRISE.max_discount_pct = 20, so a 15% discount is allowed."""
    cid = make_customer()
    r = _sub(base_url, cid, planCode="ENTERPRISE", seats=5, discountPct=15)
    assert r.status_code == 201, r.text


def test_subscription_discount_over_plan_max_400(base_url, make_customer):
    """SUBSCRIPTIONS.DISCOUNT_PCT WHEN-VALIDATE-ITEM: discount <= plan.maxDiscountPct.

    THE headline cross-field rule: a 15% discount on PRO (max_discount_pct = 0)
    must be rejected. A field-only range check (0..100) would wrongly accept it.
    """
    cid = make_customer()
    r = _sub(base_url, cid, planCode="PRO", seats=5, discountPct=15)
    assert r.status_code == 400, (
        "discount above the plan maximum must be rejected; a field-only "
        f"0..100 range check would return 201. Got {r.status_code}: {r.text}"
    )
    assert r.json()["field"] == "discountPct"


def test_subscription_enddate_before_start_400(base_url, make_customer):
    """SUBSCRIPTIONS WHEN-VALIDATE-RECORD: endDate must be after startDate."""
    cid = make_customer()
    r = _sub(base_url, cid, planCode="PRO", startDate=LATER, endDate=TODAY)
    assert r.status_code == 400
    assert r.json()["field"] == "endDate"


def test_subscription_closed_customer_400(base_url, make_customer):
    """SUBSCRIPTIONS PRE-INSERT: no subscription for a CLOSED customer."""
    cid = make_customer(status="CLOSED")
    r = _sub(base_url, cid, planCode="PRO", seats=1)
    assert r.status_code == 400
    assert "closed" in r.json()["message"].lower()
