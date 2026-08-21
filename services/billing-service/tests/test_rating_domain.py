from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain import (
    PlanRow,
    RatingResultRow,
    SubscriptionRow,
    UsageSummaryRow,
    applicable_subscription,
    finalize_rating,
    md5_uuid,
    rate_usage,
    subtract_months,
    usage_rating,
    usage_summary,
)

TENANT = UUID("00000000-0000-0000-0000-000000000001")
SUBSCRIPTION = UUID("20000000-0000-0000-0000-000000000001")
PERIOD_START = date(2026, 2, 1)
PERIOD_END = date(2026, 2, 28)

STARTER = PlanRow(
    plan_id=UUID("10000000-0000-0000-0000-000000000001"),
    code="STARTER",
    tier="starter",
    monthly_fee=Decimal("49.00"),
    included_units=100,
    overage_rate=Decimal("0.055000"),
    active=True,
)
GROWTH = replace(
    STARTER,
    plan_id=UUID("10000000-0000-0000-0000-000000000002"),
    code="GROWTH",
    tier="growth",
    monthly_fee=Decimal("149.00"),
    included_units=500,
    overage_rate=Decimal("0.035000"),
)
SCALE = replace(
    STARTER,
    plan_id=UUID("10000000-0000-0000-0000-000000000003"),
    code="SCALE",
    tier="scale",
    monthly_fee=Decimal("499.00"),
    included_units=2000,
    overage_rate=Decimal("0.020000"),
)

ACTIVE = SubscriptionRow(
    subscription_id=SUBSCRIPTION,
    tenant_id=TENANT,
    plan_id=STARTER.plan_id,
    starts_on=date(2026, 1, 1),
    ends_on=None,
    status="active",
    suspended_on=None,
)
SUSPENDED = replace(
    ACTIVE,
    plan_id=GROWTH.plan_id,
    status="suspended",
    suspended_on=date(2026, 2, 15),
)


@dataclass
class FakeRatingRepository:
    subscription: SubscriptionRow | None = ACTIVE
    plan: PlanRow | None = STARTER
    used_units: int | None = 0
    prior_rollover_units: int | None = None
    summary: list[UsageSummaryRow] = field(default_factory=list)
    results: list[RatingResultRow] = field(default_factory=list)
    periods: list[tuple] = field(default_factory=list)
    upserts: list[tuple] = field(default_factory=list)
    rollover_window: list[date] = field(default_factory=list)

    def find_rating_subscription(self, tenant_id, period_start, period_end):
        return self.subscription

    def find_plan(self, plan_id):
        return self.plan

    def sum_usage_units(self, tenant_id, period_start, period_end):
        return self.used_units

    def sum_prior_rollover_units(self, tenant_id, period_start, earliest_period_start):
        self.rollover_window.append(earliest_period_start)
        return self.prior_rollover_units

    def summarize_usage(self, tenant_id, period_start, period_end):
        return list(self.summary)

    def upsert_rating_period(self, period_id, tenant_id, period_start, period_end):
        self.periods.append((period_id, tenant_id, period_start, period_end))

    def upsert_rating_result(self, *args):
        self.upserts.append(args)

    def find_rating_results(self, period_id):
        return list(self.results)


def rate(**overrides) -> object:
    repository = FakeRatingRepository(**overrides)
    return usage_rating(repository, TENANT, PERIOD_START, PERIOD_END)


@pytest.mark.rule("RATING-R001")
def test_rating_uses_the_latest_starting_overlapping_subscription() -> None:
    older = replace(ACTIVE, subscription_id=UUID(int=1), starts_on=date(2025, 12, 1))
    newer = replace(ACTIVE, subscription_id=UUID(int=2), starts_on=date(2026, 1, 15))
    ended = replace(
        ACTIVE,
        subscription_id=UUID(int=3),
        starts_on=date(2025, 6, 1),
        ends_on=date(2026, 1, 31),
    )
    future = replace(ACTIVE, subscription_id=UUID(int=4), starts_on=date(2026, 3, 1))

    selected = applicable_subscription([older, ended, newer, future], PERIOD_START, PERIOD_END)

    assert selected == newer
    assert rate(subscription=ACTIVE, plan=GROWTH, used_units=0).quota_units == 500


@pytest.mark.rule("RATING-R002")
def test_used_units_default_to_zero_without_usage_events() -> None:
    assert rate(used_units=None).used_units == 0
    assert rate(used_units=260).used_units == 260


@pytest.mark.rule("RATING-R003")
def test_rollover_is_capped_at_twice_the_quota_over_a_three_month_window() -> None:
    assert rate(used_units=260, prior_rollover_units=300).rollover_units == 200
    assert rate(used_units=260, prior_rollover_units=150).rollover_units == 150
    assert rate(used_units=260).rollover_units == 0

    repository = FakeRatingRepository()
    usage_rating(repository, TENANT, PERIOD_START, PERIOD_END)
    assert repository.rollover_window == [date(2025, 11, 1)]
    assert subtract_months(date(2026, 3, 31), 3) == date(2025, 12, 31)


@pytest.mark.rule("RATING-R004")
def test_billable_units_subtract_rollover_and_quota_and_floor_at_zero() -> None:
    assert rate(used_units=260).billable_units == 160
    assert rate(used_units=260, prior_rollover_units=300).billable_units == 0
    assert rate(used_units=40).billable_units == 0


@pytest.mark.rule("RATING-R005")
def test_billable_units_split_across_the_101_unit_first_tier() -> None:
    boundary = rate(used_units=201)
    assert (boundary.first_tier_units, boundary.second_tier_units) == (101, 0)

    beyond = rate(used_units=202)
    assert (beyond.first_tier_units, beyond.second_tier_units) == (101, 1)


@pytest.mark.rule("RATING-R006")
def test_overage_charges_the_second_tier_at_one_and_a_half_times_the_rate() -> None:
    scale = rate(subscription=ACTIVE, plan=SCALE, used_units=2201)
    assert (scale.first_tier_units, scale.second_tier_units) == (101, 100)
    assert scale.overage_amount == Decimal("5.02")
    assert rate(used_units=201).overage_amount == Decimal("5.56")


@pytest.mark.rule("RATING-R007")
def test_suspension_prorates_billable_units_and_the_rounded_overage() -> None:
    prorated = rate(subscription=SUSPENDED, plan=GROWTH, used_units=700)
    assert prorated.billable_units == 100
    assert prorated.overage_amount == Decimal("4.37")

    outside = rate(
        subscription=replace(SUSPENDED, suspended_on=date(2026, 3, 5)),
        plan=GROWTH,
        used_units=700,
    )
    assert outside.billable_units == 200
    assert outside.overage_amount == Decimal("8.73")


@pytest.mark.rule("RATING-R008")
def test_usage_summary_is_ordered_by_kind() -> None:
    repository = FakeRatingRepository(
        summary=[
            UsageSummaryRow(kind="storage", event_count=1, units=30),
            UsageSummaryRow(kind="api", event_count=1, units=20),
        ]
    )

    rows = usage_summary(repository, TENANT, PERIOD_START, PERIOD_END)

    assert [row.kind for row in rows] == ["api", "storage"]
    assert [row.units for row in rows] == [20, 30]


@pytest.mark.rule("RATING-R009")
def test_finalize_stores_unused_quota_as_the_result_rollover() -> None:
    stored = RatingResultRow(
        used_units=260,
        quota_units=100,
        rollover_units=0,
        billable_units=0,
        overage_amount=Decimal("0.00"),
    )
    repository = FakeRatingRepository(
        used_units=260,
        prior_rollover_units=300,
        results=[stored],
    )

    rows = finalize_rating(repository, TENANT, PERIOD_START, PERIOD_END)

    period_id = md5_uuid(f"{TENANT}2026-02-01")
    assert repository.periods == [(period_id, TENANT, PERIOD_START, PERIOD_END)]
    assert repository.upserts == [
        (
            md5_uuid(str(period_id)),
            period_id,
            SUBSCRIPTION,
            260,
            100,
            0,
            0,
            Decimal("0.00"),
            datetime(2026, 2, 28, tzinfo=UTC),
        )
    ]
    assert rows == [stored]


def test_rating_row_matches_the_procedure_shape_without_a_subscription() -> None:
    row = rate_usage(None, None, None, None, TENANT, PERIOD_START, PERIOD_END)

    assert row.quota_units is None
    assert row.used_units == 0
    assert row.billable_units == 0
