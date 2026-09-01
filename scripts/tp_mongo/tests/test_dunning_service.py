"""Unit tests for the MongoDB application-side PKG_DUNNING replacement."""
from __future__ import annotations

import sys
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import mongomock
from bson import Decimal128

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.dunning_service import DunningService  # noqa: E402
from tp_mongo.rating_service import NS_VALUE, TARGET_DB, md5_uuid  # noqa: E402


class _Session:
    def __init__(self, database):
        self.database = database
        self.snapshot = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _traceback):
        if exc_type is not None and self.snapshot is not None:
            for name in self.database._db.list_collection_names():
                self.database._db[name].delete_many({})
            for name, documents in self.snapshot.items():
                if documents:
                    self.database._db[name].insert_many(deepcopy(documents))
        return False

    def start_transaction(self):
        self.snapshot = {
            name: list(self.database._db[name].find())
            for name in self.database._db.list_collection_names()
        }
        return self


class _Client:
    def __init__(self, database):
        self.database = database

    def start_session(self):
        return _Session(self.database)


class _Collection:
    def __init__(self, collection):
        self.collection = collection

    def __getattr__(self, name):
        return getattr(self.collection, name)

    def _kwargs(self, kwargs):
        kwargs.pop("session", None)
        return kwargs

    def find(self, *args, **kwargs):
        return self.collection.find(*args, **self._kwargs(kwargs))

    def find_one(self, *args, **kwargs):
        return self.collection.find_one(*args, **self._kwargs(kwargs))

    def count_documents(self, *args, **kwargs):
        return self.collection.count_documents(*args, **self._kwargs(kwargs))

    def insert_one(self, *args, **kwargs):
        return self.collection.insert_one(*args, **self._kwargs(kwargs))

    def update_one(self, *args, **kwargs):
        return self.collection.update_one(*args, **self._kwargs(kwargs))

    def update_many(self, *args, **kwargs):
        return self.collection.update_many(*args, **self._kwargs(kwargs))


class _Database:
    def __init__(self):
        self.name = TARGET_DB
        self._db = mongomock.MongoClient(tz_aware=True)["target"]
        self.client = _Client(self)

    def __getitem__(self, name):
        return _Collection(self._db[name])


def _db():
    db = _Database()
    db["tenants"].insert_many(
        [
            {"_id": "tenant-active", "status_cd": 10, "ns": NS_VALUE},
            {"_id": "tenant-suspended", "status_cd": 20, "ns": NS_VALUE},
            {"_id": "tenant-unknown", "status_cd": 99, "ns": NS_VALUE},
        ]
    )
    return db


def _invoice(invoice_id, tenant_id, issued_at, status_cd=40, **extra):
    document = {
        "_id": invoice_id,
        "tenant_id": tenant_id,
        "issued_at": datetime.combine(issued_at, datetime.min.time()).replace(
            tzinfo=timezone.utc
        ),
        "total": Decimal128("12.34"),
        "status_cd": status_cd,
        "ns": NS_VALUE,
    }
    document.update(extra)
    return document


def _attempt(invoice_id, attempt_no, tenant_id="tenant-active", status_cd=20):
    return {
        "attempt_no": attempt_no,
        "id": md5_uuid(invoice_id + str(attempt_no)),
        "tenant_id": tenant_id,
        "scheduled_for": datetime(2026, 2, 16, tzinfo=timezone.utc),
        "status_cd": status_cd,
    }


def test_overdue_accounts_ordering_days_and_tenant_status():
    db = _db()
    db["invoices"].insert_many(
        [
            _invoice("invoice-late", "tenant-unknown", date(2026, 2, 1)),
            _invoice("invoice-early", "missing", date(2026, 2, 13)),
            _invoice("invoice-suspended", "tenant-suspended", date(2026, 2, 10)),
            _invoice("invoice-active", "tenant-active", date(2026, 2, 20)),
            _invoice("invoice-issued", "tenant-active", date(2026, 2, 28)),
            _invoice("invoice-paid", "tenant-active", date(2026, 2, 1), status_cd=20),
        ]
    )

    rows = DunningService(db).overdue_accounts(date(2026, 2, 28))

    assert [row["invoice_id"] for row in rows] == [
        "invoice-late",
        "invoice-suspended",
        "invoice-early",
        "invoice-active",
    ]
    assert [row["days_overdue"] for row in rows] == [27, 18, 15, 8]
    assert [row["tenant_status"] for row in rows] == [
        "UNKNOWN",
        "suspended",
        "UNKNOWN",
        "active",
    ]
    assert rows[0]["total"] == Decimal("12.34")


def test_overdue_accounts_strict_date_boundary_and_ns_filter():
    db = _db()
    db["invoices"].insert_many(
        [
            _invoice("same-day", "tenant-active", date(2026, 2, 28)),
            _invoice("other-ns", "tenant-active", date(2026, 2, 1), ns="other"),
            _invoice("overdue", "tenant-active", date(2026, 2, 27)),
        ]
    )

    assert [row["invoice_id"] for row in DunningService(db).overdue_accounts(date(2026, 2, 28))] == [
        "overdue"
    ]


def test_schedule_attempt_numbering_weekend_shift_ids_and_metadata():
    db = _db()
    db["invoices"].insert_many(
        [
            _invoice("invoice-a", "tenant-active", date(2026, 2, 1)),
            _invoice(
                "invoice-b",
                "tenant-active",
                date(2026, 2, 2),
                dunning_attempts=[_attempt("invoice-b", 2)],
            ),
        ]
    )
    audit = []
    service = DunningService(db, audit_sink=lambda module, message: audit.append((module, message)))

    result = service.schedule_dunning(date(2026, 2, 14))

    assert result == {"scheduled": 2, "last_run_dt": date(2026, 2, 14)}
    assert audit == [("DUNNING", "scheduled 2 attempts as of 14-FEB-26")]
    assert service.scheduled_cnt == 2
    assert service.last_run_dt == date(2026, 2, 14)
    attempts = db["invoices"].find_one({"_id": "invoice-a"})["dunning_attempts"]
    assert attempts[0]["attempt_no"] == 1
    assert attempts[0]["id"] == md5_uuid("invoice-a1")
    assert attempts[0]["status_cd"] == 10
    assert attempts[0]["scheduled_for"] == datetime(
        2026, 2, 16, tzinfo=timezone.utc
    )
    assert db["invoices"].find_one({"_id": "invoice-b"})["dunning_attempts"][-1][
        "attempt_no"
    ] == 3

    weekday = DunningService(db).schedule_dunning(date(2026, 2, 17))
    assert weekday["scheduled"] == 2
    assert db["invoices"].find_one({"_id": "invoice-a"})["dunning_attempts"][-1][
        "scheduled_for"
    ] == datetime(2026, 2, 17, tzinfo=timezone.utc)
    sunday = DunningService(db).schedule_dunning(date(2026, 2, 22))
    assert sunday["scheduled"] == 2
    assert db["invoices"].find_one({"_id": "invoice-a"})["dunning_attempts"][-1][
        "scheduled_for"
    ] == datetime(2026, 2, 23, tzinfo=timezone.utc)


def test_successive_schedules_advance_attempt_numbers_and_count():
    db = _db()
    db["invoices"].insert_one(_invoice("invoice-a", "tenant-active", date(2026, 2, 1)))
    audit = []
    service = DunningService(db, audit_sink=lambda module, message: audit.append((module, message)))

    first = service.schedule_dunning(date(2026, 2, 17))
    second = service.schedule_dunning(date(2026, 2, 17))

    assert first["scheduled"] == 1
    assert second["scheduled"] == 1
    assert audit == [
        ("DUNNING", "scheduled 1 attempts as of 17-FEB-26"),
        ("DUNNING", "scheduled 1 attempts as of 17-FEB-26"),
    ]
    attempts = db["invoices"].find_one({"_id": "invoice-a"})["dunning_attempts"]
    assert [attempt["attempt_no"] for attempt in attempts] == [1, 2]
    assert all(attempt["status_cd"] == 10 for attempt in attempts)
    assert [attempt["id"] for attempt in attempts] == [
        md5_uuid("invoice-a1"),
        md5_uuid("invoice-a2"),
    ]
    assert all(
        attempt["scheduled_for"] == datetime(2026, 2, 17, tzinfo=timezone.utc)
        for attempt in attempts
    )
    assert service.scheduled_cnt == 1


def test_element_key_guard_silently_ignores_colliding_write():
    db = _db()
    invoice = _invoice("invoice-a", "tenant-active", date(2026, 2, 1))
    db["invoices"].insert_one(invoice)
    audit = []
    service = DunningService(db, audit_sink=lambda module, message: audit.append((module, message)))

    assert service._schedule_attempt(invoice, 1, date(2026, 2, 17))
    assert not service._schedule_attempt(invoice, 1, date(2026, 2, 17))
    assert len(db["invoices"].find_one({"_id": "invoice-a"})["dunning_attempts"]) == 1
    assert service.scheduled_cnt == 0


def _add_subscriptions(db):
    db["subscriptions"].insert_many(
        [
            {"_id": "active-sub", "tenant_id": "tenant-active", "status_cd": 10, "ns": NS_VALUE},
            {"_id": "suspended-sub", "tenant_id": "tenant-active", "status_cd": 20, "ns": NS_VALUE},
            {"_id": "cancelled-sub", "tenant_id": "tenant-active", "status_cd": 30, "ns": NS_VALUE},
            {"_id": "other-ns-sub", "tenant_id": "tenant-active", "status_cd": 10, "ns": "other"},
            {"_id": "already-suspended", "tenant_id": "tenant-suspended", "status_cd": 10, "ns": NS_VALUE},
        ]
    )


def test_suspend_boundary_moves_only_active_subscriptions_and_notifies_once():
    db = _db()
    _add_subscriptions(db)
    db["invoices"].insert_many(
        [
            _invoice("boundary", "tenant-active", date(2026, 2, 14)),
            _invoice("too-new", "tenant-suspended", date(2026, 2, 15)),
            _invoice("other-ns", "tenant-active", date(2026, 2, 1), ns="other"),
        ]
    )
    audit = []
    service = DunningService(
        db, audit_sink=lambda module, message: audit.append((module, message))
    )

    result = service.suspend_overdue(date(2026, 2, 28))

    assert result == {
        "suspended": ["tenant-active"],
        "notifications_inserted": 1,
    }
    assert db["tenants"].find_one({"_id": "tenant-active"})["status_cd"] == 20
    assert db["subscriptions"].find_one({"_id": "active-sub"})["status_cd"] == 20
    assert db["subscriptions"].find_one({"_id": "active-sub"})["suspended_on"] == datetime(
        2026, 2, 28, tzinfo=timezone.utc
    )
    assert db["subscriptions"].find_one({"_id": "suspended-sub"})["status_cd"] == 20
    assert db["subscriptions"].find_one({"_id": "cancelled-sub"})["status_cd"] == 30
    assert db["subscriptions"].find_one({"_id": "other-ns-sub"})["status_cd"] == 10
    notification = db["notifications"].find_one({"tenant_id": "tenant-active"})
    assert notification["_id"] == md5_uuid("tenant-activesuspension2026-02-28")
    assert notification["kind_cd"] == 3
    assert notification["sent_at"] == datetime(2026, 2, 28, tzinfo=timezone.utc)
    assert audit == [("DUNNING", "suspended tenant=tenant-active")]

    again = service.suspend_overdue(date(2026, 2, 28))
    assert again == {"suspended": [], "notifications_inserted": 0}
    assert db["notifications"].count_documents({}) == 1
    assert audit == [("DUNNING", "suspended tenant=tenant-active")]


def test_suspend_skips_nonactive_tenants_and_uses_sorted_tenant_ids():
    db = _db()
    db["invoices"].insert_many(
        [
            _invoice("invoice-unknown", "tenant-unknown", date(2026, 2, 1)),
            _invoice("invoice-suspended", "tenant-suspended", date(2026, 2, 1)),
        ]
    )
    seen = []
    service = DunningService(db, audit_sink=lambda _module, message: seen.append(message))

    result = service.suspend_overdue(date(2026, 2, 28))

    assert result == {"suspended": [], "notifications_inserted": 0}
    assert db["notifications"].count_documents({}) == 0
    assert seen == []


def test_suspend_rolls_back_all_writes_on_transaction_failure(monkeypatch):
    db = _db()
    db["invoices"].insert_one(_invoice("invoice-a", "tenant-active", date(2026, 2, 1)))
    service = DunningService(db)

    def fail(*_args, **_kwargs):
        raise RuntimeError("forced notification failure")

    monkeypatch.setattr(service.notifications, "update_one", fail)
    try:
        service.suspend_overdue(date(2026, 2, 28))
    except RuntimeError as exc:
        assert str(exc) == "forced notification failure"
    else:
        raise AssertionError("expected transaction failure")
    assert db["tenants"].find_one({"_id": "tenant-active"})["status_cd"] == 10
