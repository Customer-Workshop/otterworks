"""Unit tests for the MongoDB application-side PKG_INVOICING replacement."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import mongomock
from bson import Decimal128

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.invoicing_service import InvoicingService  # noqa: E402
from tp_mongo.rating_service import (  # noqa: E402
    NS_VALUE,
    TARGET_DB,
    Rating,
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

    def _kwargs(self, kwargs):
        kwargs.pop("session", None)
        return kwargs

    def find(self, *args, **kwargs):
        return self.collection.find(*args, **self._kwargs(kwargs))

    def find_one(self, *args, **kwargs):
        return self.collection.find_one(*args, **self._kwargs(kwargs))

    def insert_one(self, *args, **kwargs):
        return self.collection.insert_one(*args, **self._kwargs(kwargs))

    def update_one(self, *args, **kwargs):
        return self.collection.update_one(*args, **self._kwargs(kwargs))


class _Database:
    def __init__(self):
        self.name = TARGET_DB
        self.client = _Client()
        self._db = mongomock.MongoClient(tz_aware=True)["target"]

    def __getitem__(self, name):
        return _Collection(self._db[name])


class _RatingService:
    def __init__(self, db, overage=Decimal("5.56")):
        self.db = db
        self.subscription_source = __import__(
            "tp_mongo.rating_service", fromlist=["MongoSubscriptionSource"]
        ).MongoSubscriptionSource(db)
        self.overage = overage
        self.finalize_calls = []

    def compute_rating(self, tenant_id, period_start, period_end, session=None):
        return Rating(
            tenant_id,
            period_start,
            period_end,
            100,
            100,
            0,
            0,
            0,
            0,
            self.overage,
        )

    def finalize_rating(self, tenant_id, period_start, period_end):
        self.finalize_calls.append((tenant_id, period_start, period_end))


def _db(*, fee="49.00", overage=Decimal("5.56"), exempt=None, credits=()):
    db = _Database()
    db["plans"].insert_one(
        {
            "_id": "plan-1",
            "code": "STARTER",
            "monthly_fee": Decimal128(fee),
            "ns": NS_VALUE,
        }
    )
    db["subscriptions"].insert_one(
        {
            "_id": "sub-1",
            "tenant_id": "tenant-1",
            "plan_id": "plan-1",
            "starts_on": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "ends_on": None,
            "ns": NS_VALUE,
        }
    )
    db["tenants"].insert_one(
        {"_id": "tenant-1", "tax_exempt_yn": exempt, "ns": NS_VALUE}
    )
    for note_id, issued_on, remaining in credits:
        db["credit_notes"].insert_one(
            {
                "_id": note_id,
                "tenant_id": "tenant-1",
                "issued_on": datetime.fromisoformat(issued_on).replace(
                    tzinfo=timezone.utc
                ),
                "remaining_amount": Decimal128(remaining),
                "ns": NS_VALUE,
            }
        )
    return db, _RatingService(db, overage)


def _period():
    return datetime(2026, 2, 1).date(), datetime(2026, 2, 28).date()


def test_preview_propagates_null_plan_to_tax_and_cap():
    db, rating = _db()
    db["subscriptions"].update_one({}, {"$set": {"plan_id": "missing"}})
    service = InvoicingService(db, rating)

    rows = service.invoice_preview("tenant-1", *_period())

    assert rows[0]["description"] is None
    assert rows[0]["amount"] is None
    assert rows[2]["amount"] is None
    assert rows[4]["credit_applied"] == Decimal("0")


def test_exempt_tenant_has_zero_tax_and_credit_uses_least_of_cap():
    db, rating = _db(exempt="Y", credits=(("c1", "2026-02-01", "100.00"),))
    service = InvoicingService(db, rating)

    preview = service.invoice_preview("tenant-1", *_period())

    assert preview[2]["amount"] == Decimal("0")
    assert preview[4]["credit_applied"] == Decimal("54.56")
    assert preview[4]["total"] == Decimal("-54.56")


def test_preview_has_five_rows_and_unrounded_tax_halves():
    db, rating = _db(fee="49.00", overage=Decimal("5.56"))
    service = InvoicingService(db, rating)

    rows = service.invoice_preview("tenant-1", *_period())

    assert [(row["line_no"], row["line_type"]) for row in rows] == [
        (1, "plan"),
        (2, "usage"),
        (3, "tax"),
        (4, "tax"),
        (5, "credit"),
    ]
    assert rows[2]["amount"] == Decimal("2.2506")
    assert rows[3]["total"] == Decimal("2.2506")


def test_issue_inserts_then_rebuilds_lines_and_burns_oldest_credit_first():
    db, rating = _db(
        fee="44.44",
        exempt="Y",
        credits=(
            ("c1", "2026-02-01", "50.00"),
            ("c2", "2026-02-01", "6.96"),
        )
    )
    service = InvoicingService(db, rating)

    issued = service.issue_invoice("tenant-1", *_period())

    assert rating.finalize_calls
    assert issued["status_cd"] == 20
    assert [line["line_no"] for line in issued["lines"]] == [1, 2, 3, 4, 5]
    assert issued["lines"][0]["id"] == md5_uuid(issued["_id"] + "1")
    assert issued["subtotal"].to_decimal() == Decimal("50.00")
    assert issued["tax"].to_decimal() == Decimal("0.00")
    assert issued["total"].to_decimal() == Decimal("0.00")
    assert db["credit_notes"].find_one({"_id": "c1"})["remaining_amount"].to_decimal() == Decimal("0")
    assert db["credit_notes"].find_one({"_id": "c2"})["remaining_amount"].to_decimal() == Decimal("6.96")


def test_issue_update_branch_replaces_stale_lines_and_ids_are_deterministic():
    db, rating = _db(credits=())
    service = InvoicingService(db, rating)
    period_start, period_end = _period()
    invoice_id = md5_uuid(md5_uuid("tenant-1" + "2026-02-01") + "invoice")
    db["invoices"].insert_one(
        {
            "_id": invoice_id,
            "tenant_id": "tenant-1",
            "period_id": md5_uuid("tenant-1" + "2026-02-01"),
            "issued_at": datetime(2026, 1, 1),
            "subtotal": Decimal128("1.00"),
            "tax": Decimal128("2.00"),
            "total": Decimal128("3.00"),
            "status_cd": 40,
            "lines": [{"line_no": 99, "amount": Decimal128("999.00")}],
            "ns": NS_VALUE,
        }
    )

    issued = service.issue_invoice("tenant-1", period_start, period_end)

    assert [line["line_no"] for line in issued["lines"]] == [1, 2, 3, 4, 5]
    assert issued["status_cd"] == 20
    assert issued["lines"][0]["description"] == "STARTER"
    assert issued["lines"][0]["id"] == md5_uuid(invoice_id + "1")
    assert invoice_id == md5_uuid(md5_uuid("tenant-1" + "2026-02-01") + "invoice")


def test_total_rounding_is_half_away_from_zero_and_lines_project_in_order():
    db, rating = _db(fee="0.005", overage=Decimal("0"))
    service = InvoicingService(db, rating)

    issued = service.issue_invoice("tenant-1", *_period())

    assert issued["lines"][0]["amount"].to_decimal() == Decimal("0.01")
    assert service.invoice_lines(issued["_id"])[0]["line_type"] == "plan"
