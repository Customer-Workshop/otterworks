from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

from bson.decimal128 import Decimal128

from app.docstore import database
from app.domain import PlanRow, SubscriptionRow
from app.rating import RatingPeriodRow, RatingResultRow, UsageEventRow


@dataclass(frozen=True)
class CustomerRow:
    tenant_id: UUID
    name: str
    tax_exempt: bool
    status: str


def _decimal(value: Decimal128 | Decimal | str) -> Decimal:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(value)


def _date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def _timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _plan(document: dict) -> PlanRow:
    return PlanRow(
        plan_id=UUID(document["_id"]),
        code=document["code"],
        tier=document["tier"],
        monthly_fee=_decimal(document["monthly_fee"]),
        included_units=document["included_units"],
        overage_rate=_decimal(document["overage_rate"]),
        active=document["active"],
    )


def _subscription(document: dict) -> SubscriptionRow:
    return SubscriptionRow(
        subscription_id=UUID(document["_id"]),
        tenant_id=UUID(document["tenant_id"]),
        plan_id=UUID(document["plan_id"]),
        starts_on=_date(document["starts_on"]),
        ends_on=_date(document["ends_on"]),
        status=document["status"],
        suspended_on=_date(document["suspended_on"]),
    )


def _usage_event(document: dict) -> UsageEventRow:
    return UsageEventRow(
        event_id=UUID(document["_id"]),
        tenant_id=UUID(document["tenant_id"]),
        occurred_at=_timestamp(document["occurred_at"]),
        units=document["units"],
        kind=document["kind"],
    )


def _rating_result(document: dict) -> RatingResultRow:
    return RatingResultRow(
        result_id=UUID(document["result_id"]),
        subscription_id=UUID(document["subscription_id"]),
        used_units=document["used_units"],
        quota_units=document["quota_units"],
        rollover_units=document["rollover_units"],
        billable_units=document["billable_units"],
        overage_amount=_decimal(document["overage_amount"]),
        created_at=_timestamp(document["created_at"]),
    )


def _rating_period(document: dict) -> RatingPeriodRow:
    result = document.get("result")
    return RatingPeriodRow(
        period_id=UUID(document["_id"]),
        tenant_id=UUID(document["tenant_id"]),
        period_start=_date(document["period_start"]),
        period_end=_date(document["period_end"]),
        result=_rating_result(result) if result is not None else None,
    )


def _midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


class DocumentRatingRepository:
    def get_customer(self, tenant_id: UUID) -> CustomerRow | None:
        document = database()["customers"].find_one({"_id": str(tenant_id)})
        if document is None:
            return None
        return CustomerRow(
            tenant_id=UUID(document["_id"]),
            name=document["name"],
            tax_exempt=document["tax_exempt"],
            status=document["status"],
        )

    def get_plan(self, plan_id: UUID) -> PlanRow | None:
        document = database()["plans"].find_one({"_id": str(plan_id)})
        return _plan(document) if document is not None else None

    def list_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]:
        documents = database()["subscriptions"].find({"tenant_id": str(tenant_id)})
        return [_subscription(document) for document in documents]

    def list_usage_events(self, tenant_id: UUID) -> list[UsageEventRow]:
        documents = database()["usage_events"].find({"tenant_id": str(tenant_id)})
        return [_usage_event(document) for document in documents]

    def list_rating_periods(self, tenant_id: UUID) -> list[RatingPeriodRow]:
        documents = database()["rating_periods"].find({"tenant_id": str(tenant_id)})
        return [_rating_period(document) for document in documents]

    def upsert_rating_period(
        self,
        tenant_id: UUID,
        period_start: date,
        period_end: date,
        period_id: UUID,
        result: RatingResultRow,
    ) -> RatingPeriodRow:
        collection = database()["rating_periods"]
        conflict = {
            "tenant_id": str(tenant_id),
            "period_start": _midnight(period_start),
        }
        existing = collection.find_one(conflict)
        stored_period_id = existing["_id"] if existing is not None else str(period_id)
        document = {
            "_id": stored_period_id,
            "tenant_id": str(tenant_id),
            "period_start": _midnight(period_start),
            "period_end": _midnight(period_end),
            "result": {
                "result_id": str(result.result_id),
                "subscription_id": str(result.subscription_id),
                "used_units": result.used_units,
                "quota_units": result.quota_units,
                "rollover_units": result.rollover_units,
                "billable_units": result.billable_units,
                "overage_amount": Decimal128(result.overage_amount),
                "created_at": _timestamp(result.created_at),
            },
        }
        collection.replace_one(conflict, document, upsert=True)
        return RatingPeriodRow(
            UUID(stored_period_id), tenant_id, period_start, period_end, result
        )
