"""Application-side replacement for the Oracle PKG_PLANS and subscription triggers.

The autonomous pkg_ow_util.log_msg calls are intentionally outside U3 scope.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from bson import ObjectId

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
NS_FILTER = {"ns": NS_VALUE}

TIER_DECODE = {1: "starter", 2: "growth", 3: "scale"}
STATUS_DECODE = {10: "active", 20: "suspended", 30: "cancelled"}
MONTH_ABBREVIATIONS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


def _decode(mapping: dict, value):
    return mapping.get(value, "UNKNOWN")


def _effective_date(starts_on: datetime, on: datetime) -> datetime:
    """Compare Mongo dates consistently when a client returns naive UTC values."""
    if starts_on.tzinfo is None and on.tzinfo is not None:
        starts_on = starts_on.replace(tzinfo=on.tzinfo)
    elif on.tzinfo is None and starts_on.tzinfo is not None:
        on = on.replace(tzinfo=starts_on.tzinfo)
    return max(starts_on, on)


def list_plans(db) -> list[dict]:
    """Return active plans ordered by monthly fee and code."""
    query = {"active_yn": "Y", **NS_FILTER}
    cursor = db["plans"].find(
        query,
        {
            "_id": 1,
            "code": 1,
            "tier_cd": 1,
            "monthly_fee": 1,
            "included_units": 1,
            "overage_rate": 1,
        },
    ).sort([("monthly_fee", 1), ("code", 1)])
    return [
        {
            "plan_id": plan["_id"],
            "code": plan.get("code"),
            "tier": _decode(TIER_DECODE, plan.get("tier_cd")),
            "monthly_fee": plan.get("monthly_fee"),
            "included_units": plan.get("included_units"),
            "overage_rate": plan.get("overage_rate"),
        }
        for plan in cursor
    ]


def entitlement(db, tenant_id, on: datetime) -> dict | None:
    """Return the latest subscription covering ``on`` for an existing tenant."""
    if db["tenants"].find_one({"_id": tenant_id, **NS_FILTER}) is None:
        return None
    query = {
        "tenant_id": tenant_id,
        **NS_FILTER,
        "starts_on": {"$lte": on},
        "$or": [{"ends_on": None}, {"ends_on": {"$gte": on}}],
    }
    subscription = next(
        iter(db["subscriptions"].find(query).sort("starts_on", -1).limit(1)),
        None,
    )
    if subscription is None:
        return None
    plan = db["plans"].find_one({"_id": subscription.get("plan_id"), **NS_FILTER})
    return {
        "tenant_id": tenant_id,
        "plan_code": None if plan is None else plan.get("code"),
        "tier": "UNKNOWN" if plan is None else _decode(TIER_DECODE, plan.get("tier_cd")),
        "monthly_fee": None if plan is None else plan.get("monthly_fee"),
        "included_units": None if plan is None else plan.get("included_units"),
        "subscription_status": _decode(STATUS_DECODE, subscription.get("status_cd")),
        "effective_on": _effective_date(subscription["starts_on"], on),
    }


def md5_uuid(text: str) -> str:
    """Return the dashed UUID-shaped MD5 representation used by f_md5_uuid."""
    digest = hashlib.md5(text.encode("utf-8")).hexdigest().lower()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"


def hist_dt_string(now: datetime) -> str:
    """Render the trigger's DD-MON-YY HH24:MI:SS value in English."""
    return (
        f"{now.day:02d}-{MONTH_ABBREVIATIONS[now.month - 1]}-{now.year % 100:02d} "
        f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
    )


def history_doc(old_doc: dict, hist_op: str, now: datetime | None = None) -> dict:
    """Copy the old subscription row into an append-only history document."""
    if hist_op not in ("UPD", "DEL"):
        raise ValueError(f"hist_op must be UPD or DEL: {hist_op}")
    now = datetime.now(timezone.utc) if now is None else now
    return {
        "_id": ObjectId(),
        "hist_dt": hist_dt_string(now),
        "hist_op": hist_op,
        "id": old_doc.get("_id"),
        "tenant_id": old_doc.get("tenant_id"),
        "plan_id": old_doc.get("plan_id"),
        "starts_on": old_doc.get("starts_on"),
        "ends_on": old_doc.get("ends_on"),
        "status_cd": old_doc.get("status_cd"),
        "suspended_on": old_doc.get("suspended_on"),
        "ns": NS_VALUE,
    }


class SubscriptionWritePath:
    """Subscription mutations with trigger-equivalent history writes."""

    def __init__(self, db):
        if db.name != TARGET_DB:
            raise ValueError(f"write path is restricted to {TARGET_DB}: got {db.name}")
        self.db = db
        self.subscriptions = db["subscriptions"]
        self.history = db["subscriptions_hist"]

    def change_plan(self, tenant_id, plan_id, effective_on: datetime):
        new_id = md5_uuid(f"{tenant_id}{plan_id}{effective_on:%Y-%m-%d}")
        new_doc = {
            "_id": new_id,
            "tenant_id": tenant_id,
            "plan_id": plan_id,
            "starts_on": effective_on,
            "ends_on": None,
            "status_cd": 10,
            "suspended_on": None,
            "ns": NS_VALUE,
        }
        with self.db.client.start_session() as session:
            with session.start_transaction():
                if self.db["tenants"].find_one(
                    {"_id": tenant_id, **NS_FILTER}, session=session
                ) is None:
                    raise KeyError(f"no tenant with _id {tenant_id}")
                if self.db["plans"].find_one(
                    {"_id": plan_id, **NS_FILTER}, session=session
                ) is None:
                    raise KeyError(f"no plan with _id {plan_id}")
                query = {
                    "tenant_id": tenant_id,
                    **NS_FILTER,
                    "ends_on": None,
                    "starts_on": {"$lt": effective_on},
                }
                for old_doc in self.subscriptions.find(query, session=session):
                    self.history.insert_one(
                        history_doc(old_doc, "UPD"), session=session
                    )
                    status_cd = 30 if old_doc.get("status_cd") == 30 else 10
                    self.subscriptions.update_one(
                        {"_id": old_doc["_id"], **NS_FILTER},
                        {"$set": {"ends_on": effective_on - timedelta(days=1), "status_cd": status_cd}},
                        session=session,
                    )
                self.subscriptions.insert_one(new_doc, session=session)
        return new_doc

    def delete(self, sub_id):
        with self.db.client.start_session() as session:
            with session.start_transaction():
                query = {"_id": sub_id, **NS_FILTER}
                old_doc = self.subscriptions.find_one(query, session=session)
                if old_doc is None:
                    raise KeyError(f"no subscription with _id {sub_id}")
                self.history.insert_one(
                    history_doc(old_doc, "DEL"), session=session
                )
                self.subscriptions.delete_one(query, session=session)
        return old_doc

    def set_status(self, sub_id, new_status_cd):
        with self.db.client.start_session() as session:
            with session.start_transaction():
                query = {"_id": sub_id, **NS_FILTER}
                old_doc = self.subscriptions.find_one(query, session=session)
                if old_doc is None:
                    raise KeyError(f"no subscription with _id {sub_id}")
                if old_doc.get("status_cd") == 30 and new_status_cd != 30:
                    raise ValueError("cancelled subscription can never leave the cancelled state")
                self.history.insert_one(
                    history_doc(old_doc, "UPD"), session=session
                )
                self.subscriptions.update_one(
                    query, {"$set": {"status_cd": new_status_cd}}, session=session
                )
        return new_status_cd
