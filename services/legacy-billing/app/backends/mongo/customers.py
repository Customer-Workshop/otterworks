"""Unit customers: CUSTOMER_MASTER + ENTITY_ATTR_VALUE read paths (wave 1, batch w1-b01).

Ports:
  facade.py GET /customer (287-297): CUSTOMER_MASTER first-by-cust_seq_no for a tenant,
    then ENTITY_ATTR_VALUE WHERE entity_type='CUSTOMER' ORDER BY eav_id -> one find_one;
    attributes are embedded as customers.attributes[] (element key eavId, EAV_ID order).
  facade.py tenant summary customer sub-select (121-128) -> customer_summary.
  reports.py BALANCES_SQL (85-90): COUNT/SUM over conversion_batch_no -> aggregation.
Reads only; the collection is loaded by migration/load_customers.py.
"""
from decimal import Decimal

from bson.decimal128 import Decimal128

from . import db

_FIRST_FOR_TENANT = [("custSeqNo", 1)]


def _plain(value):
    return value.to_decimal() if isinstance(value, Decimal128) else value


def _yn(value):
    return None if value is None else ("Y" if value else "N")


def _money(value):
    """Match reports.py TO_CHAR(SUM(...), 'FM999999999999990.00'); Oracle SUM of no values is NULL."""
    if value is None:
        return None
    return f"{Decimal(str(value)).quantize(Decimal('0.01')):f}"


def customer_for_tenant(tenant_id):
    """GET /customer: full document, attributes[] already embedded in EAV_ID order."""
    doc = db().customers.find_one({"tenantId": tenant_id}, sort=_FIRST_FOR_TENANT)
    if not doc:
        return None
    doc = {k: _plain(v) for k, v in doc.items()}
    doc["attributes"] = [
        {k: _plain(v) for k, v in a.items()} for a in doc.get("attributes", [])
    ]
    return doc


def customer_summary(tenant_id):
    """Tenant summary sub-select: cust_no, cust_name, cur_bal_amt, past_due_amt, credit_hold_yn."""
    doc = db().customers.find_one(
        {"tenantId": tenant_id},
        sort=_FIRST_FOR_TENANT,
        projection={"custNo": 1, "custName": 1, "curBalAmt": 1, "pastDueAmt": 1, "creditHoldYn": 1},
    )
    if not doc:
        return None
    return {
        "cust_no": doc.get("custNo"),
        "cust_name": doc.get("custName"),
        "cur_bal_amt": _plain(doc.get("curBalAmt")),
        "past_due_amt": _plain(doc.get("pastDueAmt")),
        "credit_hold_yn": _yn(doc.get("creditHoldYn")),
    }


def batch_balances(batch_no):
    """reports.BALANCES_SQL: customer_count and Decimal128 sums for one conversion batch."""
    rows = list(
        db().customers.aggregate(
            [
                {"$match": {"conversionBatchNo": batch_no}},
                {
                    "$group": {
                        "_id": None,
                        "customer_count": {"$sum": 1},
                        "cur": {"$sum": "$curBalAmt"},
                        "cur_n": {"$sum": {"$cond": [{"$ne": [{"$ifNull": ["$curBalAmt", None]}, None]}, 1, 0]}},
                        "past": {"$sum": "$pastDueAmt"},
                        "past_n": {"$sum": {"$cond": [{"$ne": [{"$ifNull": ["$pastDueAmt", None]}, None]}, 1, 0]}},
                    }
                },
            ]
        )
    )
    if not rows:
        return {"customer_count": 0, "current_balance_total": None, "past_due_total": None}
    r = rows[0]
    return {
        "customer_count": r["customer_count"],
        "current_balance_total": _money(_plain(r["cur"])) if r["cur_n"] else None,
        "past_due_total": _money(_plain(r["past"])) if r["past_n"] else None,
    }
