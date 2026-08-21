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
    md5_uuid,
    next_attempt_no,
    next_business_day,
    overdue_accounts,
    schedule_dunning,
    suspend_overdue,
    tenants_to_suspend,
)

TENANT_TWO = UUID("00000000-0000-0000-0000-000000000002")
TENANT_FIVE = UUID("00000000-0000-0000-0000-000000000005")
INVOICE_ONE = UUID("60000000-0000-0000-0000-000000000001")
INVOICE_TWO = UUID("60000000-0000-0000-0000-000000000002")
PLAN = UUID("10000000-0000-0000-0000-000000000002")
SUBSCRIPTION = UUID("20000000-0000-0000-0000-000000000005")


def invoice(
    invoice_id: UUID,
    tenant_id: UUID,
    issued_on: str,
    status: str = "overdue",
    tenant_status: str = "active",
) -> InvoiceRow:
    return InvoiceRow(
        invoice_id=invoice_id,
        tenant_id=tenant_id,
        issued_at=datetime.fromisoformat(f"{issued_on}T00:00:00+00:00"),
        total=Decimal("161.29"),
        status=status,
        tenant_status=tenant_status,
    )


class FakeDunningRepository:
    def __init__(
        self,
        invoices: list[InvoiceRow],
        attempts: list[DunningAttemptRow] | None = None,
        subscriptions: list[SubscriptionRow] | None = None,
        notifications: list[NotificationRow] | None = None,
        tenant_statuses: dict[UUID, str] | None = None,
    ) -> None:
        self.invoices = invoices
        self.attempts = list(attempts or [])
        self.subscriptions = list(subscriptions or [])
        self.notifications = list(notifications or [])
        self.tenant_statuses = dict(tenant_statuses or {})
        self.suspended_tenants: list[UUID] = []

    def list_invoices(self) -> list[InvoiceRow]:
        return list(self.invoices)

    def list_dunning_attempts(self) -> list[DunningAttemptRow]:
        return list(self.attempts)

    def tenant_status(self, tenant_id: UUID) -> str | None:
        return self.tenant_statuses.get(tenant_id)

    def insert_dunning_attempt(self, attempt: DunningAttemptRow) -> None:
        clash = (attempt.invoice_id, attempt.attempt_no)
        if any((item.invoice_id, item.attempt_no) == clash for item in self.attempts):
            return
        self.attempts.append(attempt)

    def list_tenant_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]:
        return [item for item in self.subscriptions if item.tenant_id == tenant_id]

    def suspend_tenant(self, tenant_id: UUID) -> None:
        self.suspended_tenants.append(tenant_id)
        self.tenant_statuses[tenant_id] = "suspended"

    def suspend_subscription(self, subscription_id: UUID, suspended_on: date) -> None:
        self.subscriptions = [
            replace(item, status="suspended", suspended_on=suspended_on)
            if item.subscription_id == subscription_id
            else item
            for item in self.subscriptions
        ]

    def list_notifications(self) -> list[NotificationRow]:
        return list(self.notifications)

    def insert_notification(self, notification: NotificationRow) -> None:
        self.notifications.append(notification)


@pytest.mark.rule("DUNNING-001")
def test_overdue_accounts_are_ordered_and_dated_from_the_request() -> None:
    invoices = [
        invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13"),
        invoice(INVOICE_ONE, TENANT_TWO, "2026-02-01", tenant_status="suspended"),
        invoice(UUID("60000000-0000-0000-0000-000000000003"), TENANT_TWO, "2026-02-28"),
        invoice(
            UUID("60000000-0000-0000-0000-000000000004"),
            TENANT_TWO,
            "2026-01-01",
            status="issued",
        ),
    ]
    accounts = overdue_accounts(invoices, date(2026, 2, 28))
    assert [account.invoice_id for account in accounts] == [INVOICE_ONE, INVOICE_TWO]
    assert [account.days_overdue for account in accounts] == [27, 15]
    assert [account.tenant_status for account in accounts] == ["suspended", "active"]


@pytest.mark.rule("DUNNING-002")
def test_weekend_schedules_roll_forward_to_monday() -> None:
    assert next_business_day(date(2026, 2, 14)) == date(2026, 2, 16)
    assert next_business_day(date(2026, 2, 15)) == date(2026, 2, 16)
    assert next_business_day(date(2026, 2, 17)) == date(2026, 2, 17)


@pytest.mark.rule("DUNNING-003")
def test_scheduling_numbers_attempts_per_invoice_and_skips_existing_pairs() -> None:
    existing = DunningAttemptRow(
        attempt_id=UUID("80000000-0000-0000-0000-000000000001"),
        tenant_id=TENANT_FIVE,
        invoice_id=INVOICE_TWO,
        attempt_no=1,
        scheduled_for=date(2026, 2, 16),
        status="sent",
    )
    repository = FakeDunningRepository(
        invoices=[
            invoice(INVOICE_ONE, TENANT_TWO, "2026-02-01"),
            invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13"),
        ],
        attempts=[existing],
    )
    assert next_attempt_no(repository.attempts, INVOICE_TWO) == 2
    attempts, _ = schedule_dunning(repository, date(2026, 2, 17))
    assert [(str(item.invoice_id), item.attempt_no) for item in attempts] == [
        (str(INVOICE_ONE), 1),
        (str(INVOICE_TWO), 1),
        (str(INVOICE_TWO), 2),
    ]
    assert attempts[0].attempt_id == md5_uuid(f"{INVOICE_ONE}1")
    assert attempts[1].status == "sent"
    repeated, _ = schedule_dunning(repository, date(2026, 2, 18))
    assert [item.attempt_no for item in repeated] == [1, 2, 1, 2, 3]
    assert repeated[2].status == "sent"
    assert repeated[2].scheduled_for == date(2026, 2, 16)


@pytest.mark.rule("DUNNING-004")
def test_scheduling_reports_the_last_inserted_attempt() -> None:
    repository = FakeDunningRepository(
        invoices=[
            invoice(INVOICE_ONE, TENANT_TWO, "2026-02-01"),
            invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13"),
        ]
    )
    _, latest = schedule_dunning(repository, date(2026, 2, 14))
    assert (latest.invoice_id, latest.attempt_no, latest.scheduled_for, latest.status) == (
        INVOICE_TWO,
        1,
        date(2026, 2, 16),
        "scheduled",
    )
    _, repeated = schedule_dunning(repository, date(2026, 2, 14))
    assert repeated.attempt_no == 2
    assert schedule_dunning(FakeDunningRepository(invoices=[]), date(2026, 2, 14))[1] is None


@pytest.mark.rule("DUNNING-005")
def test_only_active_tenants_overdue_by_fourteen_days_are_suspended() -> None:
    invoices = [
        invoice(INVOICE_ONE, TENANT_TWO, "2026-02-01"),
        invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13"),
        invoice(UUID("60000000-0000-0000-0000-000000000003"), TENANT_FIVE, "2026-02-15"),
    ]
    assert tenants_to_suspend(invoices, date(2026, 2, 28)) == [TENANT_TWO, TENANT_FIVE]
    assert tenants_to_suspend(invoices, date(2026, 2, 20)) == [TENANT_TWO]
    repository = FakeDunningRepository(
        invoices=invoices,
        tenant_statuses={TENANT_TWO: "suspended", TENANT_FIVE: "active"},
    )
    suspend_overdue(repository, date(2026, 2, 28))
    assert repository.suspended_tenants == [TENANT_FIVE]


@pytest.mark.rule("DUNNING-006")
def test_suspension_stamps_active_subscriptions_with_the_requested_date() -> None:
    cancelled = SubscriptionRow(
        UUID("20000000-0000-0000-0000-000000000009"),
        TENANT_FIVE,
        PLAN,
        date(2025, 1, 1),
        date(2025, 12, 31),
        "cancelled",
        None,
    )
    repository = FakeDunningRepository(
        invoices=[invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13")],
        subscriptions=[
            cancelled,
            SubscriptionRow(
                SUBSCRIPTION, TENANT_FIVE, PLAN, date(2026, 1, 1), None, "active", None
            ),
        ],
        tenant_statuses={TENANT_FIVE: "active"},
    )
    _, suspended = suspend_overdue(repository, date(2026, 2, 28))
    assert [(item.status, item.suspended_on) for item in suspended] == [
        ("suspended", date(2026, 2, 28))
    ]
    assert repository.list_tenant_subscriptions(TENANT_FIVE)[0].status == "cancelled"


@pytest.mark.rule("DUNNING-007")
def test_suspension_notification_is_deterministic_and_inserted_once() -> None:
    repository = FakeDunningRepository(
        invoices=[invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13")],
        subscriptions=[
            SubscriptionRow(
                SUBSCRIPTION, TENANT_FIVE, PLAN, date(2026, 1, 1), None, "active", None
            )
        ],
        tenant_statuses={TENANT_FIVE: "active"},
    )
    notifications, _ = suspend_overdue(repository, date(2026, 2, 28))
    assert len(notifications) == 1
    assert notifications[0].notification_id == UUID("8cd558f5-d843-8d3d-be19-fb94c21ab81f")
    assert notifications[0].sent_at == datetime(2026, 2, 28, tzinfo=UTC)
    repository.tenant_statuses[TENANT_FIVE] = "active"
    repeated, _ = suspend_overdue(repository, date(2026, 2, 28))
    assert len(repeated) == 1


@pytest.mark.rule("DUNNING-008")
def test_suspension_processes_tenants_and_reports_notifications_in_tenant_order() -> None:
    invoices = [
        invoice(INVOICE_TWO, TENANT_FIVE, "2026-02-13"),
        invoice(INVOICE_ONE, TENANT_TWO, "2026-02-01"),
    ]
    repository = FakeDunningRepository(
        invoices=invoices,
        tenant_statuses={TENANT_TWO: "active", TENANT_FIVE: "active"},
    )
    notifications, _ = suspend_overdue(repository, date(2026, 2, 28))
    assert repository.suspended_tenants == [TENANT_TWO, TENANT_FIVE]
    assert [item.tenant_id for item in notifications] == [TENANT_TWO, TENANT_FIVE]
