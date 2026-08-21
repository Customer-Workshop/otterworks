from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import md5
from typing import Protocol
from uuid import UUID, uuid5

PLAN_CHANGE_NAMESPACE = UUID("d8e9df63-6e46-4d6a-b9c2-2ef6e99cb5ee")
OVERDUE = "overdue"
SUSPENDED = "suspended"
ACTIVE = "active"
SCHEDULED = "scheduled"
SUSPENSION = "suspension"
SUSPENSION_GRACE_DAYS = 14


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
class OverdueAccountRow:
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


@dataclass(frozen=True)
class SuspensionRow:
    tenant_id: UUID
    subscription_id: UUID
    status: str
    suspended_on: date


class DunningRepository(Protocol):
    def list_invoices(self) -> list[InvoiceRow]: ...

    def max_attempt_no(self, invoice_id: UUID) -> int: ...

    def insert_attempt(self, attempt: DunningAttemptRow) -> None: ...

    def list_attempts(self) -> list[DunningAttemptRow]: ...

    def tenant_is_active(self, tenant_id: UUID) -> bool: ...

    def suspend_tenant(self, tenant_id: UUID) -> None: ...

    def suspend_active_subscriptions(
        self, tenant_id: UUID, suspended_on: date
    ) -> list[SubscriptionRow]: ...

    def insert_notification(self, notification: NotificationRow) -> None: ...

    def list_notifications(self, kind: str) -> list[NotificationRow]: ...


def issued_on(invoice: InvoiceRow) -> date:
    issued_at = invoice.issued_at
    if issued_at.tzinfo is None:
        return issued_at.date()
    return issued_at.astimezone(UTC).date()


def overdue_invoices(invoices: list[InvoiceRow]) -> list[InvoiceRow]:
    return sorted(
        (invoice for invoice in invoices if invoice.status == OVERDUE),
        key=lambda invoice: (invoice.issued_at, invoice.invoice_id),
    )


def overdue_accounts(invoices: list[InvoiceRow], as_of: date) -> list[OverdueAccountRow]:
    return [
        OverdueAccountRow(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.invoice_id,
            total=invoice.total,
            days_overdue=(as_of - issued_on(invoice)).days,
            tenant_status=invoice.tenant_status,
        )
        for invoice in overdue_invoices(invoices)
        if issued_on(invoice) < as_of
    ]


def next_business_day(as_of: date) -> date:
    weekday = as_of.isoweekday()
    if weekday == 6:
        return as_of + timedelta(days=2)
    if weekday == 7:
        return as_of + timedelta(days=1)
    return as_of


def legacy_uuid(value: str) -> UUID:
    return UUID(md5(value.encode(), usedforsecurity=False).hexdigest())


def attempt_id(invoice_id: UUID, attempt_no: int) -> UUID:
    return legacy_uuid(f"{invoice_id}{attempt_no}")


def suspension_notification_id(tenant_id: UUID, as_of: date) -> UUID:
    return legacy_uuid(f"{tenant_id}{SUSPENSION}{as_of.isoformat()}")


def schedule_dunning(repository: DunningRepository, as_of: date) -> list[DunningAttemptRow]:
    scheduled_for = next_business_day(as_of)
    for invoice in overdue_invoices(repository.list_invoices()):
        attempt_no = repository.max_attempt_no(invoice.invoice_id) + 1
        repository.insert_attempt(
            DunningAttemptRow(
                attempt_id=attempt_id(invoice.invoice_id, attempt_no),
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.invoice_id,
                attempt_no=attempt_no,
                scheduled_for=scheduled_for,
                status=SCHEDULED,
            )
        )
    return repository.list_attempts()


def suspend_overdue(
    repository: DunningRepository, as_of: date
) -> tuple[list[SuspensionRow], list[NotificationRow]]:
    cutoff = as_of - timedelta(days=SUSPENSION_GRACE_DAYS)
    tenant_ids = sorted(
        {
            invoice.tenant_id
            for invoice in repository.list_invoices()
            if invoice.status == OVERDUE and issued_on(invoice) <= cutoff
        }
    )
    suspensions: list[SuspensionRow] = []
    for tenant_id in tenant_ids:
        if not repository.tenant_is_active(tenant_id):
            continue
        repository.suspend_tenant(tenant_id)
        for subscription in repository.suspend_active_subscriptions(tenant_id, as_of):
            suspensions.append(
                SuspensionRow(
                    tenant_id=tenant_id,
                    subscription_id=subscription.subscription_id,
                    status=subscription.status,
                    suspended_on=as_of,
                )
            )
        repository.insert_notification(
            NotificationRow(
                notification_id=suspension_notification_id(tenant_id, as_of),
                tenant_id=tenant_id,
                kind=SUSPENSION,
                sent_at=datetime.combine(as_of, datetime.min.time(), tzinfo=UTC),
            )
        )
    return suspensions, repository.list_notifications(SUSPENSION)
