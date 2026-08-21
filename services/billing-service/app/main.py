from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Path, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.db import connect, migrate, reset
from app.domain import (
    InvoiceLineRow,
    PreviewLine,
    catalog,
    change_plan,
    entitlement,
    invoice_lines,
    invoice_preview,
    issue_invoice,
    sql_round,
)
from app.repository import PostgresInvoicingRepository, PostgresPlansRepository


@asynccontextmanager
async def lifespan(_app: FastAPI):
    migrate()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlanChange(BaseModel):
    plan_id: UUID
    effective_on: date


class InvoiceIssue(BaseModel):
    period_start: date
    period_end: date


def money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    amount = sql_round(value, 2)
    if not amount:
        amount = abs(amount)
    return f"{amount:.2f}"


def preview_payload(line: PreviewLine) -> dict:
    return {
        "line_no": line.line_no,
        "line_type": line.line_type,
        "description": line.description,
        "amount": money(line.amount),
        "tax_amount": money(line.tax_amount),
        "credit_applied": money(line.credit_applied),
        "total": money(line.total),
    }


def line_payload(line: InvoiceLineRow) -> dict:
    return {
        "line_no": line.line_no,
        "line_type": line.line_type,
        "description": line.description,
        "amount": money(line.amount),
    }


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with connect() as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "healthy", "service": settings.app_name}


@app.post("/internal/reset", status_code=204)
def internal_reset() -> Response:
    if not settings.allow_internal_reset:
        raise HTTPException(status_code=404, detail="internal reset is disabled")
    reset()
    return Response(status_code=204)


@app.get("/api/plans")
def list_plans() -> list[dict]:
    with connect() as connection:
        plans = catalog(PostgresPlansRepository(connection).list_plans())
    return [
        {
            "plan_id": str(plan.plan_id),
            "code": plan.code,
            "tier": plan.tier,
            "monthly_fee": f"{plan.monthly_fee:.2f}",
            "included_units": plan.included_units,
            "overage_rate": f"{plan.overage_rate:.6f}",
        }
        for plan in plans
    ]


@app.get("/api/tenants/{tenant_id}/entitlement")
def get_entitlement(
    tenant_id: Annotated[UUID, Path()],
    on: Annotated[date, Query()],
) -> dict:
    with connect() as connection:
        row = entitlement(
            PostgresPlansRepository(connection).find_entitlements(tenant_id),
            tenant_id,
            on,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="entitlement not found")
    return {
        "tenant_id": str(row.tenant_id),
        "plan_code": row.plan_code,
        "tier": row.tier,
        "monthly_fee": f"{row.monthly_fee:.2f}",
        "included_units": row.included_units,
        "subscription_status": row.subscription_status,
        "effective_on": max(row.starts_on, on).isoformat(),
    }


@app.post("/api/tenants/{tenant_id}/plan-change")
def change_tenant_plan(tenant_id: Annotated[UUID, Path()], request: PlanChange) -> dict:
    try:
        with connect() as connection:
            repository = PostgresPlansRepository(connection)
            subscriptions, created = change_plan(
                repository,
                tenant_id,
                request.plan_id,
                request.effective_on,
            )
            return {
                "latest_plan": str(created.plan_id),
                "latest_start": created.starts_on.isoformat(),
                "subscriptions": [
                    {
                        "plan_id": str(item.plan_id),
                        "starts_on": item.starts_on.isoformat(),
                        "ends_on": item.ends_on.isoformat() if item.ends_on else None,
                        "status": item.status,
                    }
                    for item in subscriptions
                ],
            }
    except psycopg.errors.ForeignKeyViolation as error:
        raise HTTPException(status_code=400, detail="invalid plan change") from error
    except psycopg.errors.UniqueViolation as error:
        raise HTTPException(
            status_code=409,
            detail="this plan change has already been requested",
        ) from error


@app.get("/api/tenants/{tenant_id}/invoice-preview")
def preview_invoice(
    tenant_id: Annotated[UUID, Path()],
    period_start: Annotated[date, Query()],
    period_end: Annotated[date, Query()],
) -> list[dict]:
    with connect() as connection:
        lines = invoice_preview(
            PostgresInvoicingRepository(connection), tenant_id, period_start, period_end
        )
    return [preview_payload(line) for line in lines]


@app.post("/api/tenants/{tenant_id}/invoice")
def issue_tenant_invoice(
    tenant_id: Annotated[UUID, Path()], request: InvoiceIssue
) -> dict:
    with connect() as connection:
        issued = issue_invoice(
            PostgresInvoicingRepository(connection),
            tenant_id,
            request.period_start,
            request.period_end,
        )
    invoice = issued.invoices[0] if issued.invoices else None
    return {
        "status": invoice.status if invoice else None,
        "subtotal": money(invoice.subtotal) if invoice else None,
        "tax": money(invoice.tax) if invoice else None,
        "total": money(invoice.total) if invoice else None,
        "invoice_state": [
            {
                "status": item.status,
                "subtotal": money(item.subtotal),
                "tax": money(item.tax),
                "total": money(item.total),
            }
            for item in issued.invoices
        ],
        "credit_notes": [
            {
                "id": str(note.credit_note_id),
                "issued_on": note.issued_on.isoformat(),
                "remaining_amount": money(note.remaining_amount),
            }
            for note in issued.credit_notes
        ],
        "lines": [line_payload(line) for line in issued.lines],
    }


@app.get("/api/invoices/{invoice_id}/lines")
def list_invoice_lines(invoice_id: Annotated[UUID, Path()]) -> list[dict]:
    with connect() as connection:
        lines = invoice_lines(PostgresInvoicingRepository(connection), invoice_id)
    return [line_payload(line) for line in lines]
