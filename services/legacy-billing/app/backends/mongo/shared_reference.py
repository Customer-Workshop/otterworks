"""Unit shared-reference: CODES / TENANTS / PLANS read paths (wave 0).

Ports: pkg_plans.fn_list_plans (SQL + DECODE -> find + app-side tier label),
facade tenant summary (TENANTS LEFT JOIN CODES -> two point reads),
facade USAGE_KIND lookup (CODES by type + description -> find_one).
Reads only; the reference collections are loaded by migration/load_shared_reference.py.
"""
from decimal import Decimal

from bson.decimal128 import Decimal128

from . import db

TIER_LABELS = {1: "starter", 2: "growth", 3: "scale"}


def _plain(value):
    return value.to_decimal() if isinstance(value, Decimal128) else value


def list_plans():
    """pkg_plans.fn_list_plans: active plans ordered by monthly_fee, code."""
    cursor = db().plans.find({"activeYn": True}).sort([("monthlyFee", 1), ("code", 1)])
    return [
        {
            "plan_id": p["_id"],
            "code": p.get("code"),
            "tier": TIER_LABELS.get(p.get("tierCd"), "UNKNOWN"),
            "monthly_fee": str(_plain(p.get("monthlyFee"))) if p.get("monthlyFee") is not None else None,
            "included_units": p.get("includedUnits"),
            "overage_rate": str(_plain(p.get("overageRate"))) if p.get("overageRate") is not None else None,
        }
        for p in cursor
    ]


def code_desc(code_type, code_val):
    doc = db().codes.find_one({"_id": {"codeType": code_type, "codeVal": code_val}})
    return doc.get("codeDesc") if doc else None


def code_val(code_type, desc):
    """CODES lookup by case-insensitive description (facade usage-event kind)."""
    doc = db().codes.find_one(
        {"codeType": code_type, "codeDesc": {"$regex": f"^{desc}$", "$options": "i"}}
    )
    return doc["codeVal"] if doc else None


def tenant_summary(tenant_id):
    """facade GET tenant: TENANTS LEFT JOIN CODES(TENANT_STATUS)."""
    t = db().tenants.find_one({"_id": tenant_id})
    if not t:
        return None
    status = code_desc("TENANT_STATUS", t.get("statusCd")) if t.get("statusCd") is not None else None
    return {
        "tenant_id": t["_id"],
        "name": t.get("name"),
        "status": status,
        "tax_exempt": "Y" if t.get("taxExemptYn") else ("N" if t.get("taxExemptYn") is False else None),
    }
