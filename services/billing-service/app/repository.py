from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import psycopg

from app.domain import (
    EntitlementRow,
    PlanRow,
    RatingResultRow,
    SubscriptionRow,
    UsageSummaryRow,
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


class PostgresRatingRepository:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def find_rating_subscription(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> SubscriptionRow | None:
        row = self.connection.execute(
            """
            SELECT id, tenant_id, plan_id, starts_on, ends_on, status, suspended_on
            FROM billing_svc.subscriptions
            WHERE tenant_id = %s
              AND starts_on <= %s
              AND (ends_on IS NULL OR ends_on >= %s)
            ORDER BY starts_on DESC
            LIMIT 1
            """,
            (tenant_id, period_end, period_start),
        ).fetchone()
        if row is None:
            return None
        return SubscriptionRow(
            subscription_id=row["id"],
            tenant_id=row["tenant_id"],
            plan_id=row["plan_id"],
            starts_on=row["starts_on"],
            ends_on=row["ends_on"],
            status=row["status"],
            suspended_on=row["suspended_on"],
        )

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

    def sum_usage_units(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> int | None:
        row = self.connection.execute(
            """
            SELECT sum(units)::integer AS units
            FROM billing_svc.usage_events
            WHERE tenant_id = %s
              AND (occurred_at AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
            """,
            (tenant_id, period_start, period_end),
        ).fetchone()
        return None if row is None else row["units"]

    def sum_prior_rollover_units(
        self, tenant_id: UUID, period_start: date, earliest_period_start: date
    ) -> int | None:
        row = self.connection.execute(
            """
            SELECT sum(rr.rollover_units)::integer AS units
            FROM billing_svc.rating_results rr
            JOIN billing_svc.rating_periods rp ON rp.id = rr.period_id
            WHERE rp.tenant_id = %s
              AND rp.period_start < %s
              AND rp.period_start >= %s
            """,
            (tenant_id, period_start, earliest_period_start),
        ).fetchone()
        return None if row is None else row["units"]

    def summarize_usage(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> list[UsageSummaryRow]:
        rows = self.connection.execute(
            """
            SELECT kind, count(*) AS event_count, COALESCE(sum(units), 0) AS units
            FROM billing_svc.usage_events
            WHERE tenant_id = %s
              AND (occurred_at AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
            GROUP BY kind
            ORDER BY kind
            """,
            (tenant_id, period_start, period_end),
        ).fetchall()
        return [
            UsageSummaryRow(
                kind=row["kind"],
                event_count=int(row["event_count"]),
                units=int(row["units"]),
            )
            for row in rows
        ]

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
        subscription_id: UUID | None,
        used_units: int,
        quota_units: int,
        rollover_units: int,
        billable_units: int,
        overage_amount: Decimal,
        created_at: datetime,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO billing_svc.rating_results (
                id, period_id, subscription_id, used_units, quota_units,
                rollover_units, billable_units, overage_amount, created_at
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
                used_units,
                quota_units,
                rollover_units,
                billable_units,
                overage_amount,
                created_at,
            ),
        )

    def find_rating_results(self, period_id: UUID) -> list[RatingResultRow]:
        rows = self.connection.execute(
            """
            SELECT used_units, quota_units, rollover_units, billable_units, overage_amount
            FROM billing_svc.rating_results
            WHERE period_id = %s
            ORDER BY created_at, id
            """,
            (period_id,),
        ).fetchall()
        return [
            RatingResultRow(
                used_units=row["used_units"],
                quota_units=row["quota_units"],
                rollover_units=row["rollover_units"],
                billable_units=row["billable_units"],
                overage_amount=Decimal(row["overage_amount"]),
            )
            for row in rows
        ]
