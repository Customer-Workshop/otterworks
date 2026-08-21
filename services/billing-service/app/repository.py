from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

import psycopg

from app.domain import (
    CreditNoteRow,
    EntitlementRow,
    InvoiceLineRow,
    InvoiceRow,
    PlanRow,
    SubscriptionRow,
    TenantRow,
    UsageRating,
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


class PostgresInvoicingRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def list_overlapping_subscriptions(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> list[SubscriptionRow]:
        rows = self.connection.execute(
            """
            SELECT id, tenant_id, plan_id, starts_on, ends_on, status, suspended_on
            FROM billing_svc.subscriptions
            WHERE tenant_id = %s
              AND starts_on <= %s
              AND (ends_on IS NULL OR ends_on >= %s)
            """,
            (tenant_id, period_end, period_start),
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

    def find_plan(self, plan_id: UUID) -> PlanRow | None:
        row = self.connection.execute(
            """
            SELECT id, code, tier, monthly_fee, included_units, overage_rate, active
            FROM billing_svc.plans
            WHERE id = %s
            """,
            (plan_id,),
        ).fetchone()
        if row is None:
            return None
        return PlanRow(
            plan_id=row["id"],
            code=row["code"],
            tier=row["tier"],
            monthly_fee=Decimal(row["monthly_fee"]),
            included_units=row["included_units"],
            overage_rate=Decimal(row["overage_rate"]),
            active=row["active"],
        )

    def find_tenant(self, tenant_id: UUID) -> TenantRow | None:
        row = self.connection.execute(
            "SELECT id, tax_exempt FROM billing_svc.tenants WHERE id = %s",
            (tenant_id,),
        ).fetchone()
        if row is None:
            return None
        return TenantRow(tenant_id=row["id"], tax_exempt=row["tax_exempt"])

    def sum_usage_units(self, tenant_id: UUID, period_start: date, period_end: date) -> int:
        row = self.connection.execute(
            """
            SELECT COALESCE(sum(u.units), 0)::integer AS used_units
            FROM billing_svc.usage_events u
            WHERE u.tenant_id = %s
              AND (u.occurred_at AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
            """,
            (tenant_id, period_start, period_end),
        ).fetchone()
        return row["used_units"]

    def sum_prior_rollover_units(
        self, tenant_id: UUID, period_start: date, window_start: date
    ) -> int | None:
        row = self.connection.execute(
            """
            SELECT sum(rr.rollover_units)::integer AS rollover_units
            FROM billing_svc.rating_results rr
            JOIN billing_svc.rating_periods rp ON rp.id = rr.period_id
            WHERE rp.tenant_id = %s
              AND rp.period_start < %s
              AND rp.period_start >= %s
            """,
            (tenant_id, period_start, window_start),
        ).fetchone()
        return row["rollover_units"]

    def sum_open_credit(self, tenant_id: UUID) -> Decimal:
        row = self.connection.execute(
            """
            SELECT COALESCE(sum(remaining_amount), 0) AS open_credit
            FROM billing_svc.credit_notes
            WHERE tenant_id = %s AND remaining_amount > 0
            """,
            (tenant_id,),
        ).fetchone()
        return Decimal(row["open_credit"])

    def list_credit_notes(self, tenant_id: UUID) -> list[CreditNoteRow]:
        rows = self.connection.execute(
            """
            SELECT id, tenant_id, issued_on, amount, remaining_amount
            FROM billing_svc.credit_notes
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        ).fetchall()
        return [
            CreditNoteRow(
                credit_note_id=row["id"],
                tenant_id=row["tenant_id"],
                issued_on=row["issued_on"],
                amount=Decimal(row["amount"]),
                remaining_amount=Decimal(row["remaining_amount"]),
            )
            for row in rows
        ]

    def update_credit_note(self, credit_note_id: UUID, remaining_amount: Decimal) -> None:
        self.connection.execute(
            "UPDATE billing_svc.credit_notes SET remaining_amount = %s WHERE id = %s",
            (remaining_amount, credit_note_id),
        )

    def upsert_rating_period(
        self, period_id: UUID, tenant_id: UUID, period_start: date, period_end: date
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.rating_periods (id, tenant_id, period_start, period_end)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, period_start) DO UPDATE
              SET period_end = EXCLUDED.period_end
            """,
            (period_id, tenant_id, period_start, period_end),
        )

    def upsert_rating_result(
        self,
        result_id: UUID,
        period_id: UUID,
        subscription_id: UUID,
        rating: UsageRating,
        rollover_units: int,
        created_on: date,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.rating_results (
                id, period_id, subscription_id, used_units, quota_units, rollover_units,
                billable_units, overage_amount, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                used_units = EXCLUDED.used_units,
                rollover_units = EXCLUDED.rollover_units,
                billable_units = EXCLUDED.billable_units,
                overage_amount = EXCLUDED.overage_amount
            """,
            (
                result_id,
                period_id,
                subscription_id,
                rating.used_units,
                rating.quota_units,
                rollover_units,
                rating.billable_units,
                rating.overage_amount,
                datetime.combine(created_on, time.min),
            ),
        )

    def upsert_issued_invoice(
        self, invoice_id: UUID, tenant_id: UUID, period_id: UUID, issued_on: date
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.invoices (
                id, tenant_id, period_id, issued_at, subtotal, tax, total, status
            ) VALUES (%s, %s, %s, %s, 0, 0, 0, 'issued')
            ON CONFLICT (id) DO UPDATE SET status = 'issued'
            """,
            (invoice_id, tenant_id, period_id, datetime.combine(issued_on, time.min)),
        )

    def update_invoice_totals(
        self, invoice_id: UUID, subtotal: Decimal, tax: Decimal, total: Decimal
    ) -> None:
        self.connection.execute(
            """
            UPDATE billing_svc.invoices
               SET subtotal = %s, tax = %s, total = %s
             WHERE id = %s
            """,
            (subtotal, tax, total, invoice_id),
        )

    def list_invoices_for_period(self, period_id: UUID) -> list[InvoiceRow]:
        rows = self.connection.execute(
            """
            SELECT id, tenant_id, period_id, subtotal, tax, total, status
            FROM billing_svc.invoices
            WHERE period_id = %s
            ORDER BY id
            """,
            (period_id,),
        ).fetchall()
        return [
            InvoiceRow(
                invoice_id=row["id"],
                tenant_id=row["tenant_id"],
                period_id=row["period_id"],
                subtotal=Decimal(row["subtotal"]),
                tax=Decimal(row["tax"]),
                total=Decimal(row["total"]),
                status=row["status"],
            )
            for row in rows
        ]

    def delete_invoice_lines(self, invoice_id: UUID) -> None:
        self.connection.execute(
            "DELETE FROM billing_svc.invoice_lines WHERE invoice_id = %s",
            (invoice_id,),
        )

    def insert_invoice_line(
        self,
        line_id: UUID,
        invoice_id: UUID,
        line_no: int,
        line_type: str,
        description: str | None,
        amount: Decimal | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.invoice_lines (
                id, invoice_id, line_no, line_type, description, amount
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (line_id, invoice_id, line_no, line_type, description, amount),
        )

    def list_invoice_lines(self, invoice_id: UUID) -> list[InvoiceLineRow]:
        rows = self.connection.execute(
            """
            SELECT line_no, line_type, description, amount
            FROM billing_svc.invoice_lines
            WHERE invoice_id = %s
            """,
            (invoice_id,),
        ).fetchall()
        return [
            InvoiceLineRow(
                line_no=row["line_no"],
                line_type=row["line_type"],
                description=row["description"],
                amount=Decimal(row["amount"]),
            )
            for row in rows
        ]
