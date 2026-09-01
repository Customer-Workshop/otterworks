"""Unit tests for the U4 MongoDB rating service."""
from __future__ import annotations

import sys
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from bson import Decimal128, Int64

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.rating_service import (  # noqa: E402
    NS_VALUE,
    TARGET_DB,
    RatingResultNullValue,
    RatingService,
    RatingPeriodMissing,
    StaticSubscriptionSource,
    UsageEventRejected,
    add_months,
    md5_uuid,
)


class _InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id
        self.inserted_ids = [inserted_id]


class _FakeCollection:
    def __init__(self, docs=None, plan=None, prior=0, inserted_id="generated"):
        self.docs = list(docs or [])
        self.plan = plan
        self.prior = prior
        self.inserted_id = inserted_id
        self.aggregate_calls = []
        self.find_one_calls = []
        self.inserted = []
        self.update_many_calls = []
        self.update_one_calls = []
        self.count_calls = []
        self.find_one_error = None
        self.session_calls = []

    def find_one(self, query, session=None):
        self.find_one_calls.append(query)
        self.session_calls.append(session)
        if self.find_one_error is not None:
            raise self.find_one_error
        if "_id" in query:
            document = next(
                (
                    doc
                    for doc in self.docs + self.inserted
                    if doc.get("_id") == query["_id"]
                ),
                None,
            )
            return self.plan if document is None and self.plan is not None else document
        if "$or" in query:
            for clause in query["$or"]:
                document = next(
                    (
                        doc
                        for doc in self.docs + self.inserted
                        if all(doc.get(key) == value for key, value in clause.items())
                    ),
                    None,
                )
                if document is not None:
                    return document
            return self.plan
        if self.plan is not None:
            return self.plan
        return None

    def aggregate(self, pipeline, session=None):
        self.aggregate_calls.append(pipeline)
        self.session_calls.append(session)
        if any("$lookup" in stage for stage in pipeline):
            match = next(stage["$match"] for stage in pipeline if "$match" in stage)
            self.lookup_bounds = match["period.period_start"]
            assert isinstance(self.lookup_bounds["$lt"], datetime)
            assert isinstance(self.lookup_bounds["$gte"], datetime)
            return [{"_id": None, "rollover_units": self.prior}] if self.prior else []
        match = pipeline[0]["$match"]
        selected = [
            doc
            for doc in self.docs
            if doc.get("tenant_id") == match["tenant_id"]
            and match["occurred_at"]["$gte"]
            <= doc["occurred_at"]
            < match["occurred_at"]["$lt"]
        ]
        group = pipeline[1]["$group"]
        if group["_id"] is None:
            return [
                {
                    "_id": None,
                    "units": sum(int(doc.get("units") or 0) for doc in selected),
                }
            ] if selected else []
        labels = {1: "api", 2: "storage", 3: "compute"}
        grouped = {}
        for doc in selected:
            kind = labels.get(doc.get("kind_cd"), "UNKNOWN")
            result = grouped.setdefault(kind, {"_id": kind, "event_count": 0, "units": 0})
            result["event_count"] += 1
            result["units"] += int(doc.get("units") or 0)
        return [grouped[key] for key in sorted(grouped)]

    def insert_one(self, document, session=None):
        self.session_calls.append(session)
        self.inserted.append(document)
        return _InsertResult(document.get("_id", self.inserted_id))

    def update_many(self, query, update, session=None):
        self.session_calls.append(session)
        self.update_many_calls.append((query, update))

    def update_one(self, query, update, session=None):
        self.session_calls.append(session)
        self.update_one_calls.append((query, update))

    def count_documents(self, query):
        self.count_calls.append(query)
        return 1 if query.get("code_val") in {1, 2, 3} else 0


class _FakeDatabase:
    def __init__(self, usage=None, plan=None, prior=0):
        self.name = TARGET_DB
        self.client = _FakeClient()
        self.collections = {
            "usage_events": _FakeCollection(usage),
            "rating_periods": _FakeCollection(),
            "rating_results": _FakeCollection(prior=prior),
            "codes": _FakeCollection(),
            "plans": _FakeCollection(plan=plan),
            "subscriptions": _FakeCollection(),
        }

    def __getitem__(self, collection_name):
        return self.collections[collection_name]


class _FakeSession:
    def __init__(self):
        self.sentinel = object()
        self.committed = False
        self.aborted = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def with_transaction(self, callback):
        try:
            result = callback(self.sentinel)
        except Exception:
            self.aborted = True
            raise
        self.committed = True
        return result


class _FakeClient:
    def __init__(self):
        self.session = _FakeSession()
        self.sessions = []

    def start_session(self):
        if self.sessions:
            self.session = _FakeSession()
        self.sessions.append(self.session)
        return self.session


def _service(*, usage=None, plan=None, prior=0, subscription=None, audit=None):
    db = _FakeDatabase(usage=usage, plan=plan, prior=prior)
    return (
        RatingService(
            db,
            subscription_source=StaticSubscriptionSource(
                [] if subscription is None else [subscription]
            ),
            audit_sink=audit,
        ),
        db,
    )


def test_md5_uuid_matches_oracle_standard_hash_formatting():
    assert md5_uuid("abc") == "90015098-3cd2-4fb0-d696-3f7d28e17f72"


def test_add_months_clamps_month_end():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2024, 3, 31), -1) == date(2024, 2, 29)
    assert add_months(date(2026, 2, 28), -3) == date(2025, 11, 30)
    assert add_months(date(2026, 5, 31), -3) == date(2026, 2, 28)


def test_window_is_inclusive_by_day_and_exclusive_at_next_midnight():
    usage = [
        {
            "_id": "inside",
            "tenant_id": "t-1",
            "occurred_at": datetime(2026, 2, 28, 23, 59, 59),
            "units": Int64(7),
            "kind_cd": 1,
        },
        {
            "_id": "outside",
            "tenant_id": "t-1",
            "occurred_at": datetime(2026, 3, 1),
            "units": Int64(11),
            "kind_cd": 1,
        },
    ]
    service, db = _service(usage=usage)
    assert service.sum_usage_units("t-1", date(2026, 2, 1), date(2026, 2, 28)) == 7
    match = db.collections["usage_events"].aggregate_calls[-1][0]["$match"]
    assert match["occurred_at"] == {
        "$gte": datetime(2026, 2, 1),
        "$lt": datetime(2026, 3, 1),
    }


def test_null_plan_keeps_prior_rollover_and_zeroes_billable():
    service, _ = _service(prior=37, usage=[
        {"tenant_id": "t-1", "occurred_at": datetime(2026, 2, 5), "units": 10, "kind_cd": 1}
    ])
    rating = service.compute_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    assert rating.quota_units is None
    assert rating.rollover_units == 37
    assert rating.billable_units == 0
    assert rating.overage_amount is None


def test_rollover_is_capped_at_twice_included_units():
    service, db = _service(
        plan={"included_units": Int64(100), "overage_rate": Decimal128("1.00")},
        prior=300,
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    rating = service.compute_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    assert rating.rollover_units == 200
    bounds = db.collections["rating_results"].lookup_bounds
    assert bounds["$lt"] == datetime(2026, 2, 1)
    assert bounds["$gte"] == datetime(2025, 11, 1)


def test_tier_break_and_rounding_are_decimal_half_up():
    service, _ = _service(
        usage=[
            {
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 5),
                "units": 102,
                "kind_cd": 1,
            }
        ],
        plan={"included_units": Int64(0), "overage_rate": Decimal128("0.055")},
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    rating = service.compute_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    assert rating.first_tier_units == 101
    assert rating.second_tier_units == 1
    assert rating.overage_amount == Decimal("5.64")

    service, _ = _service(
        usage=[
            {
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 5),
                "units": 101,
                "kind_cd": 1,
            }
        ],
        plan={"included_units": Int64(0), "overage_rate": Decimal128("0.055")},
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    assert service.compute_rating(
        "t-1", date(2026, 2, 1), date(2026, 2, 28)
    ).overage_amount == Decimal("5.56")


def test_suspension_prorates_billable_and_overage_half_up():
    service, _ = _service(
        usage=[
            {
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 5),
                "units": 700,
                "kind_cd": 1,
            }
        ],
        plan={"included_units": Int64(500), "overage_rate": Decimal128("0.035")},
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
            "status_cd": 20,
            "suspended_on": date(2026, 2, 15),
        },
    )
    rating = service.compute_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    assert rating.billable_units == 100
    assert rating.overage_amount == Decimal("4.37")


def test_finalize_insert_stores_quota_minus_used_rollover():
    service, db = _service(
        usage=[
            {
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 5),
                "units": 50,
                "kind_cd": 1,
            }
        ],
        plan={"included_units": Int64(100), "overage_rate": Decimal128("1.00")},
        prior=300,
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    finalized = service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    document = db.collections["rating_results"].inserted[0]
    assert finalized["inserted_period"] is True
    assert finalized["inserted_result"] is True
    assert document["rollover_units"] == Int64(50)
    assert document["rollover_units"] != Int64(finalized["rating"].rollover_units)


def test_finalize_without_subscription_mirrors_not_null_and_aborts_transaction():
    service, db = _service()
    with pytest.raises(
        RatingResultNullValue,
        match="NOT NULL violated: rating_results.subscription_id",
    ):
        service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    # The period insert is part of the transaction and rolls back with the result error.
    assert len(db.collections["rating_periods"].inserted) == 1
    assert db.collections["rating_results"].inserted == []
    assert db.client.session.aborted is True
    assert db.client.session.committed is False


def test_finalize_without_plan_mirrors_quota_not_null_and_aborts_transaction():
    service, db = _service(
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "missing-plan",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    with pytest.raises(
        RatingResultNullValue,
        match="NOT NULL violated: rating_results.quota_units",
    ):
        service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    # The period insert is part of the transaction and rolls back with the result error.
    assert len(db.collections["rating_periods"].inserted) == 1
    assert db.collections["rating_results"].inserted == []
    assert db.client.session.aborted is True
    assert db.client.session.committed is False


def test_finalize_existing_documents_update_only_rating_values():
    service, db = _service(
        plan={"included_units": Int64(100), "overage_rate": Decimal128("1.00")},
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    period_id = md5_uuid("t-1" + "2026-02-01")
    result_id = md5_uuid(period_id)
    db.collections["rating_periods"].docs.append({"_id": period_id})
    db.collections["rating_results"].docs.append({"_id": result_id})
    finalized = service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    assert finalized["inserted_period"] is False
    assert finalized["inserted_result"] is False
    assert db.collections["rating_periods"].inserted == []
    assert db.collections["rating_results"].inserted == []
    assert db.collections["rating_periods"].update_many_calls[0][0] == {
        "tenant_id": "t-1",
        "period_start": datetime(2026, 2, 1),
    }
    assert set(db.collections["rating_results"].update_one_calls[0][1]["$set"]) == {
        "used_units",
        "rollover_units",
        "billable_units",
        "overage_amount",
    }


def test_finalize_imported_period_mirrors_fk_violation_and_aborts():
    service, db = _service(
        plan={"included_units": Int64(100), "overage_rate": Decimal128("1.00")},
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2025, 1, 1),
            "ends_on": None,
        },
    )
    db.collections["rating_periods"].docs.append(
        {
            "_id": "40000000-0000-0000-0000-000000000012",
            "tenant_id": "t-1",
            "period_start": datetime(2025, 12, 1),
            "period_end": datetime(2025, 12, 31),
        }
    )
    period_id = md5_uuid("t-1" + "2025-12-01")
    with pytest.raises(
        RatingPeriodMissing,
        match=rf"fk_rr_period violated: rating_periods\._id {period_id} is absent",
    ):
        service.finalize_rating("t-1", date(2025, 12, 1), date(2025, 12, 31))
    assert db.collections["rating_periods"].inserted == []
    assert db.collections["rating_periods"].update_many_calls[0][0] == {
        "tenant_id": "t-1",
        "period_start": datetime(2025, 12, 1),
    }
    assert db.collections["rating_results"].inserted == []
    assert db.collections["rating_results"].update_one_calls == []
    assert db.client.session.aborted is True
    assert db.client.session.committed is False


def test_finalize_rating_twice_takes_the_update_path_without_duplicate_errors():
    service, db = _service(
        usage=[
            {
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 5),
                "units": 50,
                "kind_cd": 1,
            }
        ],
        plan={"included_units": Int64(100), "overage_rate": Decimal128("1.00")},
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    first = service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    second = service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    assert first["inserted_period"] is True
    assert first["inserted_result"] is True
    assert second["inserted_period"] is False
    assert second["inserted_result"] is False
    assert second["period_id"] == first["period_id"]
    assert second["result_id"] == first["result_id"]
    assert second["rating"] == first["rating"]
    assert len(db.collections["rating_periods"].inserted) == 1
    assert len(db.collections["rating_results"].inserted) == 1
    assert db.collections["rating_periods"].update_many_calls == [
        (
            {"tenant_id": "t-1", "period_start": datetime(2026, 2, 1)},
            {"$set": {"period_end": datetime(2026, 2, 28)}},
        )
    ]
    result_query, result_update = db.collections["rating_results"].update_one_calls[0]
    assert result_query == {"_id": first["result_id"]}
    assert set(result_update["$set"]) == {
        "used_units",
        "rollover_units",
        "billable_units",
        "overage_amount",
    }
    assert len(db.client.sessions) == 2
    assert all(session.committed for session in db.client.sessions)
    assert not any(session.aborted for session in db.client.sessions)


def test_finalize_rating_uses_one_transaction_session_for_all_operations():
    service, db = _service(
        usage=[
            {
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 5),
                "units": 50,
                "kind_cd": 1,
            }
        ],
        plan={"included_units": Int64(100), "overage_rate": Decimal128("1.00")},
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    sentinel = db.client.session.sentinel
    assert set(db.collections["rating_periods"].session_calls) == {sentinel}
    assert sentinel in db.collections["usage_events"].session_calls
    assert sentinel in db.collections["rating_results"].session_calls
    assert db.client.session.committed is True
    assert db.client.session.aborted is False


def test_finalize_rating_aborts_when_plan_lookup_fails():
    service, db = _service(
        subscription={
            "_id": "sub-1",
            "tenant_id": "t-1",
            "plan_id": "plan-1",
            "starts_on": date(2026, 1, 1),
            "ends_on": None,
        },
    )
    db.collections["plans"].find_one_error = RuntimeError("plan lookup failed")
    with pytest.raises(RuntimeError, match="plan lookup failed"):
        service.finalize_rating("t-1", date(2026, 2, 1), date(2026, 2, 28))
    assert db.client.session.aborted is True
    assert db.client.session.committed is False


def test_insert_usage_event_matches_trigger_rejections_and_types():
    service, db = _service()
    with pytest.raises(UsageEventRejected, match=r"^units must be > 0$"):
        service.insert_usage_event(
            {
                "_id": "e-0",
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "units": 0,
                "kind_cd": 1,
            }
        )
    with pytest.raises(UsageEventRejected, match=r"^unknown usage kind 9$"):
        service.insert_usage_event(
            {
                "_id": "e-9",
                "tenant_id": "t-1",
                "occurred_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "units": 1,
                "kind_cd": 9,
            }
        )
    event_id = service.insert_usage_event(
        {
            "_id": "e-1",
            "tenant_id": "t-1",
            "occurred_at": datetime(
                2026, 2, 1, microsecond=123456, tzinfo=timezone.utc
            ),
            "units": 4,
            "kind_cd": 1,
        }
    )
    event = db.collections["usage_events"].inserted[0]
    assert event_id == "e-1"
    assert event["units"] == Int64(4)
    assert event["occurred_at"].microsecond == 123000
    assert event["ns"] == NS_VALUE
