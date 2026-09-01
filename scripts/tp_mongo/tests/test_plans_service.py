"""Tests for the MongoDB application-side PKG_PLANS replacement."""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mongomock
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.plans_service import (  # noqa: E402
    NS_VALUE,
    TARGET_DB,
    SubscriptionWritePath,
    entitlement,
    list_plans,
    md5_uuid,
)


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def start_transaction(self):
        return self


class _Client:
    def start_session(self):
        return _Session()


class _Collection:
    def __init__(self, collection):
        self.collection = collection

    def __getattr__(self, name):
        return getattr(self.collection, name)

    def find(self, *args, **kwargs):
        kwargs.pop("session", None)
        return self.collection.find(*args, **kwargs)

    def find_one(self, *args, **kwargs):
        kwargs.pop("session", None)
        return self.collection.find_one(*args, **kwargs)

    def insert_one(self, *args, **kwargs):
        kwargs.pop("session", None)
        return self.collection.insert_one(*args, **kwargs)

    def update_one(self, *args, **kwargs):
        kwargs.pop("session", None)
        return self.collection.update_one(*args, **kwargs)


class _Database:
    def __init__(self):
        self.name = TARGET_DB
        self.client = _Client()
        self._db = mongomock.MongoClient(tz_aware=True)["test"]

    def __getitem__(self, name):
        return _Collection(self._db[name])


def _db() -> _Database:
    return _Database()


def _plan(_id, code, fee, tier_cd=1, active_yn="Y"):
    return {
        "_id": _id,
        "code": code,
        "tier_cd": tier_cd,
        "monthly_fee": fee,
        "included_units": 100,
        "overage_rate": 1.25,
        "active_yn": active_yn,
        "ns": NS_VALUE,
    }


def _subscription(_id, tenant_id, plan_id, starts_on, ends_on=None, status_cd=10):
    return {
        "_id": _id,
        "tenant_id": tenant_id,
        "plan_id": plan_id,
        "starts_on": starts_on,
        "ends_on": ends_on,
        "status_cd": status_cd,
        "suspended_on": None,
        "ns": NS_VALUE,
    }


def test_list_plans_filters_active_and_sorts_by_fee_then_code():
    db = _db()
    db["plans"].insert_many(
        [
            _plan("p3", "Z", 5, active_yn="Y"),
            _plan("p1", "B", 5, active_yn="Y"),
            _plan("p2", "A", 2, active_yn=None),
            _plan("p4", "C", 2, active_yn="N"),
        ]
    )

    assert [(plan["monthly_fee"], plan["code"]) for plan in list_plans(db)] == [(5, "B"), (5, "Z")]


def test_list_plans_decodes_known_and_unknown_tiers():
    db = _db()
    db["plans"].insert_many(
        [_plan("p1", "START", 1, tier_cd=1), _plan("p2", "ODD", 2, tier_cd=99)]
    )

    result = list_plans(db)

    assert [plan["tier"] for plan in result] == ["starter", "UNKNOWN"]


def test_entitlement_picks_latest_covering_subscription_and_decodes_status():
    db = _db()
    on = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db["tenants"].insert_one({"_id": "t1", "ns": NS_VALUE})
    db["plans"].insert_one(_plan("p1", "GROWTH", 12, tier_cd=2))
    db["subscriptions"].insert_many(
        [
            _subscription("s1", "t1", "p1", on - timedelta(days=30), status_cd=20),
            _subscription("s2", "t1", "p1", on - timedelta(days=10), status_cd=99),
        ]
    )

    result = entitlement(db, "t1", on)

    assert result == {
        "tenant_id": "t1",
        "plan_code": "GROWTH",
        "tier": "growth",
        "monthly_fee": 12,
        "included_units": 100,
        "subscription_status": "UNKNOWN",
        "effective_on": on,
    }


def test_entitlement_respects_open_end_and_effective_greatest():
    db = _db()
    starts = datetime(2026, 9, 2, tzinfo=timezone.utc)
    on = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db["tenants"].insert_one({"_id": "t1", "ns": NS_VALUE})
    db["plans"].insert_one(_plan("p1", "START", 10))
    db["subscriptions"].insert_one(_subscription("s1", "t1", "p1", starts))

    result = entitlement(db, "t1", on)

    assert result is None
    result = entitlement(db, "t1", starts)
    assert result["effective_on"] == starts


def test_entitlement_returns_none_for_missing_tenant():
    db = _db()
    assert entitlement(db, "missing", datetime.now(timezone.utc)) is None


def test_entitlement_missing_plan_is_outer_join_with_unknown_values():
    db = _db()
    on = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db["tenants"].insert_one({"_id": "t1", "ns": NS_VALUE})
    db["subscriptions"].insert_one(_subscription("s1", "t1", "missing", on, status_cd=30))

    assert entitlement(db, "t1", on) == {
        "tenant_id": "t1",
        "plan_code": None,
        "tier": "UNKNOWN",
        "monthly_fee": None,
        "included_units": None,
        "subscription_status": "cancelled",
        "effective_on": on,
    }


def test_md5_uuid_matches_known_vector_and_uuid_shape():
    text = "t1p12026-09-01"
    expected = hashlib.md5(text.encode("utf-8")).hexdigest()
    result = md5_uuid(text)

    assert result.replace("-", "") == expected
    assert re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", result)


def test_change_plan_closes_open_subscriptions_and_writes_old_history():
    db = _db()
    effective = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db["subscriptions"].insert_many(
        [
            _subscription("s1", "t1", "old", effective - timedelta(days=30), status_cd=30),
            _subscription("s2", "t1", "old", effective - timedelta(days=20), status_cd=20),
            _subscription("s3", "t1", "old", effective, status_cd=10),
        ]
    )

    new_doc = SubscriptionWritePath(db).change_plan("t1", "p1", effective)

    assert new_doc["_id"] == md5_uuid("t1p12026-09-01")
    closed = list(db["subscriptions"].find({"_id": {"$in": ["s1", "s2"]}}))
    assert {doc["ends_on"] for doc in closed} == {effective - timedelta(days=1)}
    assert {doc["_id"]: doc["status_cd"] for doc in closed} == {"s1": 30, "s2": 10}
    assert db["subscriptions"].find_one({"_id": "s3"})["ends_on"] is None
    history = list(db["subscriptions_hist"].find({}))
    assert len(history) == 2
    assert all(doc["hist_op"] == "UPD" and doc["ns"] == NS_VALUE for doc in history)
    assert {doc["id"] for doc in history} == {"s1", "s2"}
    assert {doc["status_cd"] for doc in history} == {20, 30}
    assert db["subscriptions"].find_one({"_id": new_doc["_id"]})["status_cd"] == 10


def test_set_status_rejects_uncancel_and_allows_valid_transitions_with_history():
    db = _db()
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    db["subscriptions"].insert_many(
        [_subscription("cancelled", "t1", "p1", now, status_cd=30), _subscription("active", "t1", "p1", now)]
    )
    path = SubscriptionWritePath(db)

    with pytest.raises(ValueError, match="cancelled subscription can never leave"):
        path.set_status("cancelled", 10)
    assert db["subscriptions_hist"].count_documents({}) == 0
    path.set_status("cancelled", 30)
    path.set_status("active", 20)

    assert db["subscriptions"].find_one({"_id": "cancelled"})["status_cd"] == 30
    assert db["subscriptions"].find_one({"_id": "active"})["status_cd"] == 20
    history = list(db["subscriptions_hist"].find({}))
    assert len(history) == 2
    assert {doc["id"] for doc in history} == {"cancelled", "active"}


def test_write_path_refuses_wrong_database():
    db = _db()
    db.name = "ow_tp_mongodb_032752_quarantine"
    with pytest.raises(ValueError):
        SubscriptionWritePath(db)
