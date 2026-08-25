from __future__ import annotations

import hashlib
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import UUID

from app.domain import PlanRow, SubscriptionRow

MONEY_QUANTUM = Decimal("0.01")
INTEGER_QUANTUM = Decimal("1")


@dataclass(frozen=True)
class UsageEventRow:
    event_id: UUID
    tenant_id: UUID
    occurred_at: datetime
    units: int
    kind: str


@dataclass(frozen=True)
class RatingResultRow:
    result_id: UUID
    subscription_id: UUID
    used_units: int
    quota_units: int
    rollover_units: int
    billable_units: int
    overage_amount: Decimal
    created_at: datetime


@dataclass(frozen=True)
class RatingPeriodRow:
    period_id: UUID
    tenant_id: UUID
    period_start: date
    period_end: date
    result: RatingResultRow | None


@dataclass(frozen=True)
class Rating:
    subscription_id: UUID
    used_units: int
    quota_units: int
    rollover_units: int
    billable_units: int
    first_tier_units: int
    second_tier_units: int
    overage_amount: Decimal


class RatingRepository(Protocol):
    def get_plan(self, plan_id: UUID) -> PlanRow | None: ...

    def list_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]: ...

    def list_usage_events(self, tenant_id: UUID) -> list[UsageEventRow]: ...

    def list_rating_periods(self, tenant_id: UUID) -> list[RatingPeriodRow]: ...

    def upsert_rating_period(
        self,
        tenant_id: UUID,
        period_start: date,
        period_end: date,
        period_id: UUID,
        result: RatingResultRow,
    ) -> RatingPeriodRow: ...


class RatingNotFoundError(LookupError):
    pass


def three_months_prior(value: date) -> date:
    month_index = value.year * 12 + value.month - 1 - 3
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def period_id_for(tenant_id: UUID, period_start: date) -> UUID:
    return UUID(hashlib.md5(f"{tenant_id}{period_start.isoformat()}".encode()).hexdigest())


def result_id_for(period_id: UUID) -> UUID:
    return UUID(hashlib.md5(str(period_id).encode()).hexdigest())


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _rounded_integer(value: Decimal) -> int:
    return int(value.quantize(INTEGER_QUANTUM, rounding=ROUND_HALF_UP))


def _subscription(
    subscriptions: list[SubscriptionRow], period_start: date, period_end: date
) -> SubscriptionRow | None:
    overlapping = [
        subscription
        for subscription in subscriptions
        if subscription.starts_on <= period_end
        and (subscription.ends_on is None or subscription.ends_on >= period_start)
    ]
    return max(overlapping, key=lambda subscription: subscription.starts_on, default=None)


def rate(
    repository: RatingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> Rating:
    subscription = _subscription(repository.list_subscriptions(tenant_id), period_start, period_end)
    if subscription is None:
        raise RatingNotFoundError("rating subscription not found")
    plan = repository.get_plan(subscription.plan_id)
    if plan is None:
        raise RatingNotFoundError("rating plan not found")

    used_units = sum(
        event.units
        for event in repository.list_usage_events(tenant_id)
        if period_start <= event.occurred_at.date() <= period_end
    )
    window_start = three_months_prior(period_start)
    prior_rollover = sum(
        period.result.rollover_units
        for period in repository.list_rating_periods(tenant_id)
        if period.result is not None
        and window_start <= period.period_start < period_start
    )
    prior_rollover = min(2 * plan.included_units, prior_rollover)
    rollover_units = min(prior_rollover, plan.included_units * 2)
    billable_units = max(used_units - rollover_units - plan.included_units, 0)
    first_tier_units = min(billable_units, 101)
    second_tier_units = max(billable_units - 101, 0)
    overage_amount = _money(
        Decimal(first_tier_units) * plan.overage_rate
        + Decimal(second_tier_units) * plan.overage_rate * Decimal("1.5")
    )

    if (
        subscription.status == "suspended"
        and subscription.suspended_on is not None
        and period_start <= subscription.suspended_on <= period_end
    ):
        period_days = Decimal((period_end - period_start).days + 1)
        suspended_days = Decimal((period_end - subscription.suspended_on).days + 1)
        proration = suspended_days / period_days
        billable_units = _rounded_integer(Decimal(billable_units) * proration)
        overage_amount = _money(overage_amount * proration)

    return Rating(
        subscription_id=subscription.subscription_id,
        used_units=used_units,
        quota_units=plan.included_units,
        rollover_units=rollover_units,
        billable_units=billable_units,
        first_tier_units=first_tier_units,
        second_tier_units=second_tier_units,
        overage_amount=overage_amount,
    )


def usage_summary(
    repository: RatingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> list[dict[str, int | str]]:
    summary: dict[str, dict[str, int]] = {}
    for event in repository.list_usage_events(tenant_id):
        if period_start <= event.occurred_at.date() <= period_end:
            row = summary.setdefault(event.kind, {"event_count": 0, "units": 0})
            row["event_count"] += 1
            row["units"] += event.units
    return [
        {"kind": kind, "event_count": values["event_count"], "units": values["units"]}
        for kind, values in sorted(summary.items())
    ]


def finalize(
    repository: RatingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> RatingPeriodRow:
    result = rate(repository, tenant_id, period_start, period_end)
    persisted_result = RatingResultRow(
        result_id=result_id_for(period_id_for(tenant_id, period_start)),
        subscription_id=result.subscription_id,
        used_units=result.used_units,
        quota_units=result.quota_units,
        rollover_units=max(result.quota_units - result.used_units, 0),
        billable_units=result.billable_units,
        overage_amount=result.overage_amount,
        created_at=datetime.combine(period_end, datetime.min.time(), tzinfo=UTC),
    )
    return repository.upsert_rating_period(
        tenant_id,
        period_start,
        period_end,
        period_id_for(tenant_id, period_start),
        persisted_result,
    )
