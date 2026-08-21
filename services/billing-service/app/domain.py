from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from hashlib import md5
from typing import Protocol
from uuid import UUID, uuid5

PLAN_CHANGE_NAMESPACE = UUID("d8e9df63-6e46-4d6a-b9c2-2ef6e99cb5ee")
SUSPENSION_THRESHOLD_DAYS = 14


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
class InvoiceRow:
    invoice_id: UUID
    tenant_id: UUID
    issued_at: datetime
    total: Decimal
    status: str
    tenant_status: str


@dataclass(frozen=True)
class OverdueAccount:
    tenant_id: UUID
    invoice_id: UUID
    total: Decimal
    days_overdue: int
    tenant_status: str


@dataclass(frozen=True)
class DunningAttemptRow:
    attempt_id: UUID
    tenant_id: UUID
    invoice_id: UUID
    attempt_no: int
    scheduled_for: date
    status: str


@dataclass(frozen=True)
class NotificationRow:
    notification_id: UUID
    tenant_id: UUID
    kind: str
    sent_at: datetime


class DunningRepository(Protocol):
    def list_invoices(self) -> list[InvoiceRow]: ...

    def list_dunning_attempts(self) -> list[DunningAttemptRow]: ...

    def tenant_status(self, tenant_id: UUID) -> str | None: ...

    def insert_dunning_attempt(self, attempt: DunningAttemptRow) -> None: ...

    def list_tenant_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]: ...

    def suspend_tenant(self, tenant_id: UUID) -> None: ...

    def suspend_subscription(self, subscription_id: UUID, suspended_on: date) -> None: ...

    def list_notifications(self) -> list[NotificationRow]: ...

    def insert_notification(self, notification: NotificationRow) -> None: ...


def md5_uuid(value: str) -> UUID:
    return UUID(md5(value.encode(), usedforsecurity=False).hexdigest())


def issued_on(invoice: InvoiceRow) -> date:
    return invoice.issued_at.date()


def overdue_accounts(invoices: list[InvoiceRow], as_of: date) -> list[OverdueAccount]:
    selected = [
        invoice
        for invoice in invoices
        if invoice.status == "overdue" and issued_on(invoice) < as_of
    ]
    selected.sort(key=lambda invoice: (invoice.issued_at, invoice.invoice_id))
    return [
        OverdueAccount(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            total=invoice.total,
            days_overdue=(as_of - issued_on(invoice)).days,
            tenant_status=invoice.tenant_status,
        )
        for invoice in selected
    ]


def next_business_day(day: date) -> date:
    if day.isoweekday() == 6:
        return day + timedelta(days=2)
    if day.isoweekday() == 7:
        return day + timedelta(days=1)
    return day


def next_attempt_no(attempts: list[DunningAttemptRow], invoice_id: UUID) -> int:
    existing = [item.attempt_no for item in attempts if item.invoice_id == invoice_id]
    return max(existing, default=0) + 1


def schedule_dunning(
    repository: DunningRepository, as_of: date
) -> tuple[list[DunningAttemptRow], DunningAttemptRow | None]:
    invoices = [invoice for invoice in repository.list_invoices() if invoice.status == "overdue"]
    invoices.sort(key=lambda invoice: (invoice.issued_at, invoice.invoice_id))
    scheduled_for = next_business_day(as_of)
    latest: DunningAttemptRow | None = None
    for invoice in invoices:
        attempts = repository.list_dunning_attempts()
        attempt_no = next_attempt_no(attempts, invoice.invoice_id)
        if any(
            item.invoice_id == invoice.invoice_id and item.attempt_no == attempt_no
            for item in attempts
        ):
            continue
        attempt = DunningAttemptRow(
            attempt_id=md5_uuid(f"{invoice.invoice_id}{attempt_no}"),
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            attempt_no=attempt_no,
            scheduled_for=scheduled_for,
            status="scheduled",
        )
        repository.insert_dunning_attempt(attempt)
        latest = attempt
    attempts = sorted(
        repository.list_dunning_attempts(),
        key=lambda item: (str(item.invoice_id), item.attempt_no),
    )
    return attempts, latest


def tenants_to_suspend(invoices: list[InvoiceRow], as_of: date) -> list[UUID]:
    cutoff = as_of - timedelta(days=SUSPENSION_THRESHOLD_DAYS)
    tenant_ids = {
        invoice.tenant_id
        for invoice in invoices
        if invoice.status == "overdue" and issued_on(invoice) <= cutoff
    }
    return sorted(tenant_ids, key=str)


def suspend_overdue(
    repository: DunningRepository, as_of: date
) -> tuple[list[NotificationRow], list[SubscriptionRow]]:
    invoices = repository.list_invoices()
    suspended: list[SubscriptionRow] = []
    for tenant_id in tenants_to_suspend(invoices, as_of):
        if repository.tenant_status(tenant_id) != "active":
            continue
        repository.suspend_tenant(tenant_id)
        for subscription in repository.list_tenant_subscriptions(tenant_id):
            if subscription.status != "active":
                continue
            repository.suspend_subscription(subscription.subscription_id, as_of)
            suspended.append(
                replace(subscription, status="suspended", suspended_on=as_of)
            )
        sent_at = datetime.combine(as_of, time.min, tzinfo=UTC)
        if not any(
            item.tenant_id == tenant_id and item.kind == "suspension" and item.sent_at == sent_at
            for item in repository.list_notifications()
        ):
            repository.insert_notification(
                NotificationRow(
                    notification_id=md5_uuid(f"{tenant_id}suspension{as_of.isoformat()}"),
                    tenant_id=tenant_id,
                    kind="suspension",
                    sent_at=sent_at,
                )
            )
    notifications = sorted(
        (item for item in repository.list_notifications() if item.kind == "suspension"),
        key=lambda item: (str(item.tenant_id), item.sent_at),
    )
    return notifications, suspended
