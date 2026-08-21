from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal
from uuid import UUID

import psycopg

from app.domain import (
    DunningAttemptRow,
    EntitlementRow,
    InvoiceRow,
    NotificationRow,
    PlanRow,
    SubscriptionRow,
)


class PostgresPlansRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def list_plans(self) -> list[PlanRow]:
        rows = self.connection.execute(
            """
            SELECT id, code, tier, monthly_fee, included_units, overage_rate, active
            FROM billing_svc.plans
            """
        ).fetchall()
        return [
            PlanRow(
                plan_id=row["id"],
                code=row["code"],
                tier=row["tier"],
                monthly_fee=Decimal(row["monthly_fee"]),
                included_units=row["included_units"],
                overage_rate=Decimal(row["overage_rate"]),
                active=row["active"],
            )
            for row in rows
        ]

    def find_entitlements(self, tenant_id: UUID) -> list[EntitlementRow]:
        rows = self.connection.execute(
            """
            SELECT t.id AS tenant_id, p.code AS plan_code, p.tier,
                   p.monthly_fee, p.included_units, s.status,
                   s.starts_on, s.ends_on
            FROM billing_svc.tenants t
            JOIN billing_svc.subscriptions s ON s.tenant_id = t.id
            JOIN billing_svc.plans p ON p.id = s.plan_id
            WHERE t.id = %s
            """,
            (tenant_id,),
        ).fetchall()
        return [
            EntitlementRow(
                tenant_id=row["tenant_id"],
                plan_code=row["plan_code"],
                tier=row["tier"],
                monthly_fee=Decimal(row["monthly_fee"]),
                included_units=row["included_units"],
                subscription_status=row["status"],
                ends_on=row["ends_on"],
                starts_on=row["starts_on"],
            )
            for row in rows
        ]

    def list_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]:
        rows = self.connection.execute(
            """
            SELECT id, tenant_id, plan_id, starts_on, ends_on, status, suspended_on
            FROM billing_svc.subscriptions
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        ).fetchall()
        return [
            SubscriptionRow(
                subscription_id=row["id"],
                tenant_id=row["tenant_id"],
                plan_id=row["plan_id"],
                starts_on=row["starts_on"],
                ends_on=row["ends_on"],
                status=row["status"],
                suspended_on=row["suspended_on"],
            )
            for row in rows
        ]

    def update_subscription(self, subscription_id: UUID, ends_on: date, status: str) -> None:
        self.connection.execute(
            """
            UPDATE billing_svc.subscriptions
            SET ends_on = %s, status = %s
            WHERE id = %s
            """,
            (ends_on, status, subscription_id),
        )

    def insert_subscription(
        self,
        subscription_id: UUID,
        tenant_id: UUID,
        plan_id: UUID,
        starts_on: date,
        status: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.subscriptions
                (id, tenant_id, plan_id, starts_on, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (subscription_id, tenant_id, plan_id, starts_on, status),
        )


class PostgresDunningRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def list_invoices(self) -> list[InvoiceRow]:
        rows = self.connection.execute(
            """
            SELECT i.id, i.tenant_id, i.issued_at, i.total, i.status,
                   t.status AS tenant_status
            FROM billing_svc.invoices i
            JOIN billing_svc.tenants t ON t.id = i.tenant_id
            """
        ).fetchall()
        return [
            InvoiceRow(
                invoice_id=row["id"],
                tenant_id=row["tenant_id"],
                issued_at=row["issued_at"].astimezone(UTC),
                total=Decimal(row["total"]),
                status=row["status"],
                tenant_status=row["tenant_status"],
            )
            for row in rows
        ]

    def list_dunning_attempts(self) -> list[DunningAttemptRow]:
        rows = self.connection.execute(
            """
            SELECT id, tenant_id, invoice_id, attempt_no, scheduled_for, status
            FROM billing_svc.dunning_attempts
            """
        ).fetchall()
        return [
            DunningAttemptRow(
                attempt_id=row["id"],
                tenant_id=row["tenant_id"],
                invoice_id=row["invoice_id"],
                attempt_no=row["attempt_no"],
                scheduled_for=row["scheduled_for"],
                status=row["status"],
            )
            for row in rows
        ]

    def tenant_status(self, tenant_id: UUID) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM billing_svc.tenants WHERE id = %s",
            (tenant_id,),
        ).fetchone()
        return row["status"] if row else None

    def insert_dunning_attempt(self, attempt: DunningAttemptRow) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.dunning_attempts
                (id, tenant_id, invoice_id, attempt_no, scheduled_for, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (invoice_id, attempt_no) DO NOTHING
            """,
            (
                attempt.attempt_id,
                attempt.tenant_id,
                attempt.invoice_id,
                attempt.attempt_no,
                attempt.scheduled_for,
                attempt.status,
            ),
        )

    def list_tenant_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]:
        rows = self.connection.execute(
            """
            SELECT id, tenant_id, plan_id, starts_on, ends_on, status, suspended_on
            FROM billing_svc.subscriptions
            WHERE tenant_id = %s
            ORDER BY starts_on, id
            """,
            (tenant_id,),
        ).fetchall()
        return [
            SubscriptionRow(
                subscription_id=row["id"],
                tenant_id=row["tenant_id"],
                plan_id=row["plan_id"],
                starts_on=row["starts_on"],
                ends_on=row["ends_on"],
                status=row["status"],
                suspended_on=row["suspended_on"],
            )
            for row in rows
        ]

    def suspend_tenant(self, tenant_id: UUID) -> None:
        self.connection.execute(
            "UPDATE billing_svc.tenants SET status = 'suspended' WHERE id = %s",
            (tenant_id,),
        )

    def suspend_subscription(self, subscription_id: UUID, suspended_on: date) -> None:
        self.connection.execute(
            """
            UPDATE billing_svc.subscriptions
            SET status = 'suspended', suspended_on = %s
            WHERE id = %s
            """,
            (suspended_on, subscription_id),
        )

    def list_notifications(self) -> list[NotificationRow]:
        rows = self.connection.execute(
            """
            SELECT id, tenant_id, kind, sent_at
            FROM billing_svc.notifications
            """
        ).fetchall()
        return [
            NotificationRow(
                notification_id=row["id"],
                tenant_id=row["tenant_id"],
                kind=row["kind"],
                sent_at=row["sent_at"].astimezone(UTC),
            )
            for row in rows
        ]

    def insert_notification(self, notification: NotificationRow) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.notifications (id, tenant_id, kind, sent_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, kind, sent_at) DO NOTHING
            """,
            (
                notification.notification_id,
                notification.tenant_id,
                notification.kind,
                notification.sent_at,
            ),
        )
