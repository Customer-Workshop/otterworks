from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain import PlanRow, SubscriptionRow
from app.rating import (
    RatingPeriodRow,
    RatingResultRow,
    UsageEventRow,
    finalize,
    rate,
    three_months_prior,
    usage_summary,
)

TENANT = UUID("00000000-0000-0000-0000-000000000001")
PLAN = UUID("10000000-0000-0000-0000-000000000001")
SUBSCRIPTION = UUID("20000000-0000-0000-0000-000000000001")
PERIOD = date(2026, 2, 1)
END = date(2026, 2, 28)


@dataclass
class FakeRepository:
    subscriptions: list[SubscriptionRow]
    plans: list[PlanRow]
    events: list[UsageEventRow]
    periods: list[RatingPeriodRow]
    upserts: list[RatingPeriodRow]

    def get_plan(self, plan_id: UUID) -> PlanRow | None:
        return next((plan for plan in self.plans if plan.plan_id == plan_id), None)

    def list_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]:
        return [item for item in self.subscriptions if item.tenant_id == tenant_id]

    def list_usage_events(self, tenant_id: UUID) -> list[UsageEventRow]:
        return [item for item in self.events if item.tenant_id == tenant_id]

    def list_rating_periods(self, tenant_id: UUID) -> list[RatingPeriodRow]:
        return [item for item in self.periods if item.tenant_id == tenant_id]

    def upsert_rating_period(
        self,
        tenant_id: UUID,
        period_start: date,
        period_end: date,
        period_id: UUID,
        result: RatingResultRow,
    ) -> RatingPeriodRow:
        existing = next(
            (
                item
                for item in self.periods
                if item.tenant_id == tenant_id and item.period_start == period_start
            ),
            None,
        )
        stored_period_id = existing.period_id if existing is not None else period_id
        row = RatingPeriodRow(stored_period_id, tenant_id, period_start, period_end, result)
        self.upserts.append(row)
        self.periods = [
            item
            for item in self.periods
            if not (item.tenant_id == tenant_id and item.period_start == period_start)
        ]
        self.periods.append(row)
        return row


def repository(
    *,
    used_units: int = 0,
    included_units: int = 100,
    overage_rate: Decimal = Decimal("0.055"),
    status: str = "active",
    suspended_on: date | None = None,
    periods: list[RatingPeriodRow] | None = None,
) -> FakeRepository:
    return FakeRepository(
        subscriptions=[
            SubscriptionRow(
                SUBSCRIPTION, TENANT, PLAN, date(2026, 1, 1), None, status, suspended_on
            )
        ],
        plans=[
            PlanRow(
                PLAN,
                "STARTER",
                "starter",
                Decimal("49"),
                included_units,
                overage_rate,
                True,
            )
        ],
        events=[
            UsageEventRow(
                UUID("30000000-0000-0000-0000-000000000001"),
                TENANT,
                datetime(2026, 2, 10, tzinfo=UTC),
                used_units,
                "api",
            )
        ],
        periods=periods or [],
        upserts=[],
    )


@pytest.mark.rule("RATING-R001")
def test_rate_selects_latest_overlapping_subscription() -> None:
    old = SubscriptionRow(SUBSCRIPTION, TENANT, PLAN, date(2026, 1, 1), None, "active", None)
    newer = SubscriptionRow(
        UUID("20000000-0000-0000-0000-000000000002"),
        TENANT,
        PLAN,
        date(2026, 2, 1),
        None,
        "active",
        None,
    )
    repo = repository(used_units=260)
    repo.subscriptions = [old, newer]
    assert rate(repo, TENANT, PERIOD, END).subscription_id == newer.subscription_id


@pytest.mark.rule("RATING-R002")
def test_rate_uses_selected_plan_quota_and_rate() -> None:
    result = rate(
        repository(used_units=601, included_units=500, overage_rate=Decimal("0.035")),
        TENANT,
        PERIOD,
        END,
    )
    assert result.quota_units == 500
    assert result.overage_amount == Decimal("3.54")


@pytest.mark.rule("RATING-R003")
def test_rate_includes_events_on_both_period_endpoints() -> None:
    repo = repository()
    repo.events.append(
        UsageEventRow(
            UUID("30000000-0000-0000-0000-000000000002"),
            TENANT,
            datetime(2026, 2, 28, 23, 59, tzinfo=UTC),
            10,
            "api",
        )
    )
    assert rate(repo, TENANT, PERIOD, END).used_units == 10


@pytest.mark.rule("RATING-R004")
def test_rate_sums_rollover_inside_three_month_window() -> None:
    prior = RatingPeriodRow(
        UUID("40000000-0000-0000-0000-000000000001"),
        TENANT,
        date(2025, 12, 1),
        date(2025, 12, 31),
        RatingResultRow(
            UUID("50000000-0000-0000-0000-000000000001"),
            SUBSCRIPTION,
            0,
            100,
            100,
            0,
            Decimal("0.00"),
            datetime(2025, 12, 31, tzinfo=UTC),
        ),
    )
    result = rate(repository(used_units=300, periods=[prior]), TENANT, PERIOD, END)
    assert result.rollover_units == 100


@pytest.mark.rule("RATING-R005")
def test_rate_applies_rollover_cap_twice() -> None:
    prior = RatingPeriodRow(
        UUID("40000000-0000-0000-0000-000000000001"),
        TENANT,
        date(2025, 12, 1),
        date(2025, 12, 31),
        RatingResultRow(
            UUID("50000000-0000-0000-0000-000000000001"),
            SUBSCRIPTION,
            0,
            100,
            500,
            0,
            Decimal("0.00"),
            datetime(2025, 12, 31, tzinfo=UTC),
        ),
    )
    result = rate(repository(used_units=300, periods=[prior]), TENANT, PERIOD, END)
    assert result.rollover_units == 200


@pytest.mark.rule("RATING-R006")
def test_rate_floors_billable_units_at_zero() -> None:
    result = rate(repository(used_units=100), TENANT, PERIOD, END)
    assert result.billable_units == 0


@pytest.mark.rule("RATING-R007")
def test_rate_splits_billable_units_at_101() -> None:
    result = rate(repository(used_units=302), TENANT, PERIOD, END)
    assert (result.first_tier_units, result.second_tier_units) == (101, 101)


@pytest.mark.rule("RATING-R008")
def test_rate_rounds_money_half_up_with_decimal_arithmetic() -> None:
    result = rate(repository(used_units=201), TENANT, PERIOD, END)
    assert result.overage_amount == Decimal("5.56")


@pytest.mark.rule("RATING-R009")
def test_rate_prorates_suspended_subscription_from_suspension_to_period_end() -> None:
    result = rate(
        repository(
            used_units=700,
            included_units=500,
            overage_rate=Decimal("0.035"),
            status="suspended",
            suspended_on=date(2026, 2, 15),
        ),
        TENANT,
        PERIOD,
        END,
    )
    assert (result.billable_units, result.overage_amount) == (100, Decimal("4.37"))


@pytest.mark.rule("RATING-R010")
def test_usage_summary_groups_and_orders_kinds() -> None:
    repo = repository()
    repo.events.extend(
        [
            UsageEventRow(
                UUID("30000000-0000-0000-0000-000000000002"),
                TENANT,
                datetime(2026, 2, 11, tzinfo=UTC),
                30,
                "storage",
            ),
            UsageEventRow(
                UUID("30000000-0000-0000-0000-000000000003"),
                TENANT,
                datetime(2026, 2, 12, tzinfo=UTC),
                20,
                "api",
            ),
        ]
    )
    assert usage_summary(repo, TENANT, PERIOD, END) == [
        {"kind": "api", "event_count": 2, "units": 20},
        {"kind": "storage", "event_count": 1, "units": 30},
    ]


@pytest.mark.rule("RATING-R011")
def test_finalize_upserts_period_and_refreshes_end_date() -> None:
    repo = repository(used_units=260)
    persisted = finalize(repo, TENANT, PERIOD, date(2026, 3, 1))
    assert len(repo.upserts) == 1
    assert persisted.period_end == date(2026, 3, 1)


@pytest.mark.rule("RATING-R011")
def test_finalize_updates_existing_period_without_changing_its_id() -> None:
    existing = RatingPeriodRow(
        UUID("40000000-0000-0000-0000-000000000002"),
        TENANT,
        date(2026, 1, 1),
        date(2026, 1, 30),
        None,
    )
    repo = repository(used_units=260, periods=[existing])
    persisted = finalize(repo, TENANT, date(2026, 1, 1), date(2026, 1, 31))
    matching = [
        item
        for item in repo.periods
        if item.tenant_id == TENANT and item.period_start == date(2026, 1, 1)
    ]
    assert persisted.period_id == existing.period_id
    assert persisted.period_end == date(2026, 1, 31)
    assert len(matching) == 1
    assert matching[0].period_id == existing.period_id
    assert matching[0].period_end == date(2026, 1, 31)
    assert matching[0].result == persisted.result


@pytest.mark.rule("RATING-R012")
def test_finalize_persists_unused_quota_not_carried_in_rollover() -> None:
    prior = RatingPeriodRow(
        UUID("40000000-0000-0000-0000-000000000001"),
        TENANT,
        date(2026, 1, 1),
        date(2026, 1, 31),
        RatingResultRow(
            UUID("50000000-0000-0000-0000-000000000001"),
            SUBSCRIPTION,
            0,
            100,
            200,
            0,
            Decimal("0.00"),
            datetime(2026, 1, 31, tzinfo=UTC),
        ),
    )
    persisted = finalize(repository(used_units=260, periods=[prior]), TENANT, PERIOD, END)
    assert persisted.result.rollover_units == 0


@pytest.mark.rule("RATING-R013")
def test_rate_rejects_missing_subscription_or_plan() -> None:
    repo = repository()
    repo.subscriptions = []
    with pytest.raises(LookupError):
        rate(repo, TENANT, PERIOD, END)
    repo = repository()
    repo.plans = []
    with pytest.raises(LookupError):
        rate(repo, TENANT, PERIOD, END)


def test_three_month_window_clamps_end_of_month() -> None:
    assert three_months_prior(date(2026, 5, 31)) == date(2026, 2, 28)
