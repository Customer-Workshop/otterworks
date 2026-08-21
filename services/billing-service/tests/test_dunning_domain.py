from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain import (
    DunningAttemptRow,
    InvoiceRow,
    NotificationRow,
    SubscriptionRow,
    attempt_id,
    next_business_day,
    overdue_accounts,
    schedule_dunning,
    suspend_overdue,
    suspension_notification_id,
)

TENANT_TWO = UUID("00000000-0000-0000-0000-000000000002")
TENANT_FIVE = UUID("00000000-0000-0000-0000-000000000005")
TENANT_SIX = UUID("00000000-0000-0000-0000-000000000006")
INVOICE_ONE = UUID("60000000-0000-0000-0000-000000000001")
INVOICE_TWO = UUID("60000000-0000-0000-0000-000000000002")
INVOICE_THREE = UUID("60000000-0000-0000-0000-000000000003")
SUBSCRIPTION_FIVE = UUID("20000000-0000-0000-0000-000000000005")
PLAN = UUID("10000000-0000-0000-0000-000000000002")


def invoice(
    invoice_id: UUID,
    tenant_id: UUID,
    issued_at: str,
    status: str,
    tenant_status: str,
) -> InvoiceRow:
    return InvoiceRow(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        issued_at=datetime.fromisoformat(issued_at),
        total=Decimal("161.29"),
        status=status,
        tenant_status=tenant_status,
    )


SEEDED_INVOICES = [
    invoice(INVOICE_THREE, TENANT_SIX, "2026-02-28T00:00:00+00:00", "issued", "active"),
    invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13T00:00:00+00:00", "overdue", "active"),
    invoice(INVOICE_ONE, TENANT_TWO, "2026-02-01T00:00:00+00:00", "overdue", "suspended"),
]


class FakeDunningRepository:
    def __init__(
        self,
        invoices: list[InvoiceRow] | None = None,
        attempts: list[DunningAttemptRow] | None = None,
        tenant_status: dict[UUID, str] | None = None,
        subscriptions: list[SubscriptionRow] | None = None,
        notifications: list[NotificationRow] | None = None,
    ) -> None:
        self.invoices = list(invoices if invoices is not None else SEEDED_INVOICES)
        self.attempts = list(attempts or [])
        self.tenant_status = dict(
            tenant_status
            if tenant_status is not None
            else {TENANT_TWO: "suspended", TENANT_FIVE: "active", TENANT_SIX: "active"}
        )
        self.subscriptions = list(subscriptions or [])
        self.notifications = list(notifications or [])

    def list_invoices(self) -> list[InvoiceRow]:
        return list(self.invoices)

    def max_attempt_no(self, invoice_id: UUID) -> int:
        return max(
            (item.attempt_no for item in self.attempts if item.invoice_id == invoice_id),
            default=0,
        )

    def insert_attempt(self, attempt: DunningAttemptRow) -> None:
        if any(
            item.invoice_id == attempt.invoice_id and item.attempt_no == attempt.attempt_no
            for item in self.attempts
        ):
            return
        self.attempts.append(attempt)

    def list_attempts(self) -> list[DunningAttemptRow]:
        return sorted(self.attempts, key=lambda item: (item.invoice_id, item.attempt_no))

    def tenant_is_active(self, tenant_id: UUID) -> bool:
        return self.tenant_status.get(tenant_id) == "active"

    def suspend_tenant(self, tenant_id: UUID) -> None:
        self.tenant_status[tenant_id] = "suspended"

    def suspend_active_subscriptions(
        self, tenant_id: UUID, suspended_on: date
    ) -> list[SubscriptionRow]:
        updated = []
        for index, item in enumerate(self.subscriptions):
            if item.tenant_id == tenant_id and item.status == "active":
                item = replace(item, status="suspended", suspended_on=suspended_on)
                self.subscriptions[index] = item
                updated.append(item)
        return updated

    def insert_notification(self, notification: NotificationRow) -> None:
        if any(
            item.tenant_id == notification.tenant_id
            and item.kind == notification.kind
            and item.sent_at == notification.sent_at
            for item in self.notifications
        ):
            return
        self.notifications.append(notification)

    def list_notifications(self, kind: str) -> list[NotificationRow]:
        return sorted(
            (item for item in self.notifications if item.kind == kind),
            key=lambda item: (item.tenant_id, item.sent_at),
        )


def active_subscription() -> SubscriptionRow:
    return SubscriptionRow(
        SUBSCRIPTION_FIVE, TENANT_FIVE, PLAN, date(2026, 1, 1), None, "active", None
    )


@pytest.mark.rule("DUNNING-001")
def test_overdue_accounts_filter_and_order() -> None:
    accounts = overdue_accounts(SEEDED_INVOICES, date(2026, 2, 28))
    assert [account.invoice_id for account in accounts] == [INVOICE_ONE, INVOICE_TWO]
    assert [account.tenant_status for account in accounts] == ["suspended", "active"]


@pytest.mark.rule("DUNNING-001")
def test_overdue_accounts_exclude_invoices_issued_on_the_as_of_date() -> None:
    accounts = overdue_accounts(SEEDED_INVOICES, date(2026, 2, 13))
    assert [account.invoice_id for account in accounts] == [INVOICE_ONE]


@pytest.mark.rule("DUNNING-002")
def test_days_overdue_and_total_keep_exact_values() -> None:
    accounts = overdue_accounts(SEEDED_INVOICES, date(2026, 2, 28))
    assert [account.days_overdue for account in accounts] == [27, 15]
    assert accounts[0].total == Decimal("161.29")


@pytest.mark.rule("DUNNING-003")
def test_schedule_walks_every_overdue_invoice_in_issue_order() -> None:
    repository = FakeDunningRepository()
    schedule_dunning(repository, date(2026, 2, 17))
    assert [item.invoice_id for item in repository.attempts] == [INVOICE_ONE, INVOICE_TWO]


@pytest.mark.rule("DUNNING-004")
def test_attempt_number_continues_from_the_invoice_maximum() -> None:
    existing = DunningAttemptRow(
        UUID("80000000-0000-0000-0000-000000000001"),
        TENANT_FIVE,
        INVOICE_TWO,
        1,
        date(2026, 2, 16),
        "sent",
    )
    repository = FakeDunningRepository(attempts=[existing])
    attempts = schedule_dunning(repository, date(2026, 2, 17))
    numbers = {(item.invoice_id, item.attempt_no) for item in attempts}
    assert numbers == {(INVOICE_ONE, 1), (INVOICE_TWO, 1), (INVOICE_TWO, 2)}


@pytest.mark.rule("DUNNING-005")
def test_weekend_as_of_dates_roll_forward_to_monday() -> None:
    assert next_business_day(date(2026, 2, 14)) == date(2026, 2, 16)
    assert next_business_day(date(2026, 2, 15)) == date(2026, 2, 16)
    assert next_business_day(date(2026, 2, 17)) == date(2026, 2, 17)
    assert next_business_day(date(2026, 2, 20)) == date(2026, 2, 20)


@pytest.mark.rule("DUNNING-006")
def test_attempts_are_scheduled_with_deterministic_ids_and_ignore_repeats() -> None:
    repository = FakeDunningRepository()
    schedule_dunning(repository, date(2026, 2, 17))
    schedule_dunning(repository, date(2026, 2, 18))
    first = repository.list_attempts()[0]
    assert first.status == "scheduled"
    assert first.attempt_id == attempt_id(INVOICE_ONE, 1)
    assert first.scheduled_for == date(2026, 2, 17)
    assert [(item.invoice_id, item.attempt_no) for item in repository.list_attempts()] == [
        (INVOICE_ONE, 1),
        (INVOICE_ONE, 2),
        (INVOICE_TWO, 1),
        (INVOICE_TWO, 2),
    ]


@pytest.mark.rule("DUNNING-007")
def test_suspension_skips_recent_invoices_and_already_suspended_tenants() -> None:
    repository = FakeDunningRepository(subscriptions=[active_subscription()])
    suspend_overdue(repository, date(2026, 2, 26))
    assert repository.tenant_status[TENANT_FIVE] == "active"
    assert repository.tenant_status[TENANT_TWO] == "suspended"
    assert repository.notifications == []

    suspend_overdue(repository, date(2026, 2, 27))
    assert repository.tenant_status[TENANT_FIVE] == "suspended"


@pytest.mark.rule("DUNNING-008")
def test_suspension_suspends_active_subscriptions_with_the_as_of_date() -> None:
    repository = FakeDunningRepository(subscriptions=[active_subscription()])
    suspensions, _ = suspend_overdue(repository, date(2026, 2, 28))
    assert [(item.status, item.suspended_on) for item in suspensions] == [
        ("suspended", date(2026, 2, 28))
    ]
    assert repository.subscriptions[0].suspended_on == date(2026, 2, 28)


@pytest.mark.rule("DUNNING-009")
def test_suspension_notification_is_written_once_per_tenant_and_date() -> None:
    repository = FakeDunningRepository(subscriptions=[active_subscription()])
    suspend_overdue(repository, date(2026, 2, 28))
    repository.tenant_status[TENANT_FIVE] = "active"
    _, notifications = suspend_overdue(repository, date(2026, 2, 28))
    assert len(notifications) == 1
    assert notifications[0].notification_id == suspension_notification_id(
        TENANT_FIVE, date(2026, 2, 28)
    )
    assert notifications[0].notification_id == UUID("8cd558f5-d843-8d3d-be19-fb94c21ab81f")
    assert notifications[0].sent_at == datetime(2026, 2, 28, tzinfo=UTC)
