from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from hashlib import md5
from typing import Protocol
from uuid import UUID, uuid5

PLAN_CHANGE_NAMESPACE = UUID("d8e9df63-6e46-4d6a-b9c2-2ef6e99cb5ee")
FIRST_TIER_UNITS = 101
SECOND_TIER_MULTIPLIER = Decimal("1.5")
ROLLOVER_LOOKBACK_MONTHS = 3


@dataclass(frozen=True)
class PlanRow:
    plan_id: UUID
    code: str
    tier: str
    monthly_fee: Decimal
    included_units: int
    overage_rate: Decimal
    active: bool


@dataclass(frozen=True)
class SubscriptionRow:
    subscription_id: UUID
    tenant_id: UUID
    plan_id: UUID
    starts_on: date
    ends_on: date | None
    status: str
    suspended_on: date | None


@dataclass(frozen=True)
class EntitlementRow:
    tenant_id: UUID
    plan_code: str
    tier: str
    monthly_fee: Decimal
    included_units: int
    subscription_status: str
    ends_on: date | None
    starts_on: date


class PlansRepository(Protocol):
    def list_plans(self) -> list[PlanRow]: ...

    def find_entitlements(self, tenant_id: UUID) -> list[EntitlementRow]: ...

    def list_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]: ...

    def update_subscription(self, subscription_id: UUID, ends_on: date, status: str) -> None: ...

    def insert_subscription(
        self,
        subscription_id: UUID,
        tenant_id: UUID,
        plan_id: UUID,
        starts_on: date,
        status: str,
    ) -> None: ...


def catalog(plans: list[PlanRow]) -> list[PlanRow]:
    return sorted(
        (plan for plan in plans if plan.active),
        key=lambda plan: (plan.monthly_fee, plan.code),
    )


def entitlement(rows: list[EntitlementRow], tenant_id: UUID, on: date) -> EntitlementRow | None:
    eligible = [
        row
        for row in rows
        if row.tenant_id == tenant_id
        and row.starts_on <= on
        and (row.ends_on is None or row.ends_on >= on)
    ]
    return max(eligible, key=lambda row: row.starts_on, default=None)


def change_plan(
    repository: PlansRepository,
    tenant_id: UUID,
    plan_id: UUID,
    effective_on: date,
) -> tuple[list[SubscriptionRow], SubscriptionRow]:
    subscriptions = repository.list_subscriptions(tenant_id)
    for subscription in subscriptions:
        if subscription.ends_on is None and subscription.starts_on < effective_on:
            next_status = (
                subscription.status if subscription.status == "cancelled" else "active"
            )
            repository.update_subscription(
                subscription.subscription_id,
                effective_on - timedelta(days=1),
                next_status,
            )
    created_id = uuid5(PLAN_CHANGE_NAMESPACE, f"{tenant_id}{plan_id}{effective_on.isoformat()}")
    repository.insert_subscription(
        created_id,
        tenant_id,
        plan_id,
        effective_on,
        "active",
    )
    subscriptions = sorted(
        repository.list_subscriptions(tenant_id), key=lambda item: item.starts_on
    )
    created = next(item for item in subscriptions if item.subscription_id == created_id)
    return subscriptions, created


@dataclass(frozen=True)
class UsageSummaryRow:
    kind: str
    event_count: int
    units: int


@dataclass(frozen=True)
class RatingRow:
    tenant_id: UUID
    period_start: date
    period_end: date
    used_units: int | None
    quota_units: int | None
    rollover_units: int | None
    billable_units: int | None
    first_tier_units: int | None
    second_tier_units: int | None
    overage_amount: Decimal | None


@dataclass(frozen=True)
class RatingResultRow:
    used_units: int
    quota_units: int
    rollover_units: int
    billable_units: int
    overage_amount: Decimal


class RatingRepository(Protocol):
    def find_rating_subscription(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> SubscriptionRow | None: ...

    def find_plan(self, plan_id: UUID) -> PlanRow | None: ...

    def sum_usage_units(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> int | None: ...

    def sum_prior_rollover_units(
        self, tenant_id: UUID, period_start: date, earliest_period_start: date
    ) -> int | None: ...

    def summarize_usage(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> list[UsageSummaryRow]: ...

    def upsert_rating_period(
        self, period_id: UUID, tenant_id: UUID, period_start: date, period_end: date
    ) -> None: ...

    def upsert_rating_result(
        self,
        result_id: UUID,
        period_id: UUID,
        subscription_id: UUID | None,
        used_units: int,
        quota_units: int,
        rollover_units: int,
        billable_units: int,
        overage_amount: Decimal,
        created_at: datetime,
    ) -> None: ...

    def find_rating_results(self, period_id: UUID) -> list[RatingResultRow]: ...


def sql_least(*values: int | Decimal | None) -> int | Decimal | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def sql_greatest(*values: int | Decimal | None) -> int | Decimal | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def round_half_up(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def subtract_months(anchor: date, months: int) -> date:
    total = anchor.year * 12 + (anchor.month - 1) - months
    year, month = divmod(total, 12)
    day = min(anchor.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def md5_uuid(value: str) -> UUID:
    return UUID(md5(value.encode(), usedforsecurity=False).hexdigest())


def applicable_subscription(
    subscriptions: list[SubscriptionRow], period_start: date, period_end: date
) -> SubscriptionRow | None:
    eligible = [
        item
        for item in subscriptions
        if item.starts_on <= period_end and (item.ends_on is None or item.ends_on >= period_start)
    ]
    return max(eligible, key=lambda item: item.starts_on, default=None)


def rate_usage(
    subscription: SubscriptionRow | None,
    plan: PlanRow | None,
    used_units: int | None,
    prior_rollover_units: int | None,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> RatingRow:
    included_units = plan.included_units if plan is not None else None
    doubled_quota = None if included_units is None else 2 * included_units
    prior = sql_least(doubled_quota, prior_rollover_units or 0)
    rollover = sql_least(prior, doubled_quota)
    used = used_units or 0
    net = None if included_units is None or rollover is None else used - rollover - included_units
    billable = sql_greatest(net, 0)
    first_tier = sql_least(billable, FIRST_TIER_UNITS)
    second_tier = sql_greatest(
        None if billable is None else billable - FIRST_TIER_UNITS,
        0,
    )
    rate = plan.overage_rate if plan is not None else None
    amount = (
        None
        if rate is None or first_tier is None or second_tier is None
        else round_half_up(
            first_tier * rate + second_tier * rate * SECOND_TIER_MULTIPLIER,
            2,
        )
    )
    if (
        subscription is not None
        and subscription.status == "suspended"
        and subscription.suspended_on is not None
        and period_start <= subscription.suspended_on <= period_end
    ):
        suspended_days = (period_end - subscription.suspended_on).days + 1
        period_days = (period_end - period_start).days + 1
        ratio = Decimal(suspended_days) / Decimal(period_days)
        if billable is not None:
            billable = int(round_half_up(Decimal(billable) * ratio, 0))
        if amount is not None:
            amount = round_half_up(amount * ratio, 2)
    return RatingRow(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        used_units=used,
        quota_units=included_units,
        rollover_units=rollover,
        billable_units=billable,
        first_tier_units=first_tier,
        second_tier_units=second_tier,
        overage_amount=amount,
    )


def usage_rating(
    repository: RatingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> RatingRow:
    subscription = repository.find_rating_subscription(tenant_id, period_start, period_end)
    plan = None if subscription is None else repository.find_plan(subscription.plan_id)
    used_units = repository.sum_usage_units(tenant_id, period_start, period_end)
    prior_rollover = repository.sum_prior_rollover_units(
        tenant_id,
        period_start,
        subtract_months(period_start, ROLLOVER_LOOKBACK_MONTHS),
    )
    return rate_usage(
        subscription,
        plan,
        used_units,
        prior_rollover,
        tenant_id,
        period_start,
        period_end,
    )


def usage_summary(
    repository: RatingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> list[UsageSummaryRow]:
    rows = repository.summarize_usage(tenant_id, period_start, period_end)
    return sorted(rows, key=lambda row: row.kind)


def finalize_rating(
    repository: RatingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> list[RatingResultRow]:
    period_id = md5_uuid(f"{tenant_id}{period_start.isoformat()}")
    subscription = repository.find_rating_subscription(tenant_id, period_start, period_end)
    repository.upsert_rating_period(period_id, tenant_id, period_start, period_end)
    rating = rate_usage(
        subscription,
        None if subscription is None else repository.find_plan(subscription.plan_id),
        repository.sum_usage_units(tenant_id, period_start, period_end),
        repository.sum_prior_rollover_units(
            tenant_id,
            period_start,
            subtract_months(period_start, ROLLOVER_LOOKBACK_MONTHS),
        ),
        tenant_id,
        period_start,
        period_end,
    )
    repository.upsert_rating_result(
        md5_uuid(str(period_id)),
        period_id,
        None if subscription is None else subscription.subscription_id,
        rating.used_units,
        rating.quota_units,
        sql_greatest(
            None
            if rating.quota_units is None or rating.used_units is None
            else rating.quota_units - rating.used_units,
            0,
        ),
        rating.billable_units,
        rating.overage_amount,
        datetime.combine(period_end, datetime.min.time(), tzinfo=UTC),
    )
    return repository.find_rating_results(period_id)
