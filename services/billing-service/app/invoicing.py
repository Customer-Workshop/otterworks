from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import UUID

from app.domain import PlanRow
from app.rating import RatingRepository, _subscription, finalize, period_id_for, rate

MONEY_QUANTUM = Decimal("0.01")
TAX_RATE = Decimal("0.0825")


@dataclass(frozen=True)
class CustomerRow:
    tenant_id: UUID
    name: str
    tax_exempt: bool
    status: str


@dataclass(frozen=True)
class CreditNoteRow:
    note_id: UUID
    tenant_id: UUID
    issued_on: date
    amount: Decimal
    remaining_amount: Decimal


@dataclass(frozen=True)
class InvoiceLineRow:
    line_no: int
    line_type: str
    description: str
    amount: Decimal


@dataclass(frozen=True)
class InvoiceRow:
    invoice_id: UUID
    tenant_id: UUID
    period_id: UUID
    issued_at: datetime
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: str
    lines: list[InvoiceLineRow]


@dataclass(frozen=True)
class PreviewLine:
    line_no: int
    line_type: str
    description: str
    amount: Decimal
    tax_amount: Decimal
    credit_applied: Decimal
    total: Decimal


class InvoiceNotFoundError(LookupError):
    pass


class InvoicingRepository(RatingRepository, Protocol):
    def get_customer(self, tenant_id: UUID) -> CustomerRow | None: ...

    def list_credit_notes(self, tenant_id: UUID) -> list[CreditNoteRow]: ...

    def get_invoice(self, invoice_id: UUID) -> InvoiceRow | None: ...

    def upsert_invoice(
        self,
        tenant_id: UUID,
        period_id: UUID,
        invoice_id: UUID,
        issued_at: datetime,
        subtotal: Decimal,
        tax: Decimal,
        total: Decimal,
        status: str,
        lines: list[InvoiceLineRow],
    ) -> InvoiceRow: ...

    def update_credit_note(self, note_id: UUID, remaining_amount: Decimal) -> None: ...


def invoice_id_for(period_id: UUID) -> UUID:
    return UUID(hashlib.md5(f"{period_id}invoice".encode()).hexdigest())


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _plan(
    repository: InvoicingRepository, tenant_id: UUID, period_start: date, period_end: date
) -> PlanRow:
    subscription = _subscription(
        repository.list_subscriptions(tenant_id), period_start, period_end
    )
    if subscription is None:
        raise InvoiceNotFoundError("invoice subscription not found")
    plan = repository.get_plan(subscription.plan_id)
    if plan is None:
        raise InvoiceNotFoundError("invoice plan not found")
    return plan


def preview(
    repository: InvoicingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> list[PreviewLine]:
    plan = _plan(repository, tenant_id, period_start, period_end)
    customer = repository.get_customer(tenant_id)
    if customer is None:
        raise InvoiceNotFoundError("invoice customer not found")
    rating = rate(repository, tenant_id, period_start, period_end)
    fee = _money(plan.monthly_fee)
    usage = _money(rating.overage_amount)
    tax = (
        Decimal("0.00")
        if customer.tax_exempt
        else (fee + usage) * TAX_RATE
    )
    available_credit = sum(
        (
            note.remaining_amount
            for note in repository.list_credit_notes(tenant_id)
            if note.remaining_amount > 0
        ),
        Decimal("0.00"),
    )
    credit_applied = min(available_credit, _money(fee + usage + tax))
    credit_total = Decimal("0.00") if credit_applied == 0 else -credit_applied
    return [
        PreviewLine(1, "plan", plan.code, fee, Decimal("0.00"), Decimal("0.00"), fee),
        PreviewLine(
            2,
            "usage",
            "usage overage",
            usage,
            Decimal("0.00"),
            Decimal("0.00"),
            usage,
        ),
        PreviewLine(
            3,
            "tax",
            "regional tax",
            tax / 2,
            Decimal("0.00"),
            Decimal("0.00"),
            tax / 2,
        ),
        PreviewLine(
            4,
            "tax",
            "local tax",
            tax / 2,
            Decimal("0.00"),
            Decimal("0.00"),
            tax / 2,
        ),
        PreviewLine(
            5,
            "credit",
            "credit notes",
            Decimal("0.00"),
            Decimal("0.00"),
            credit_applied,
            credit_total,
        ),
    ]


def issue(
    repository: InvoicingRepository,
    tenant_id: UUID,
    period_start: date,
    period_end: date,
) -> tuple[InvoiceRow, list[CreditNoteRow]]:
    finalize(repository, tenant_id, period_start, period_end)
    lines = preview(repository, tenant_id, period_start, period_end)
    subtotal = _money(
        sum(
            (_money(line.amount) for line in lines if line.line_type in {"plan", "usage"}),
            Decimal("0.00"),
        )
    )
    tax = _money(
        sum(
            (_money(line.amount) for line in lines if line.line_type == "tax"),
            Decimal("0.00"),
        )
    )
    credit_applied = next(line.credit_applied for line in lines if line.line_type == "credit")
    total = _money(subtotal + tax - credit_applied)
    persisted_lines = [
        InvoiceLineRow(
            line.line_no,
            line.line_type,
            line.description,
            line.total if line.line_type == "credit" else line.amount,
        )
        for line in lines
    ]
    period_id = period_id_for(tenant_id, period_start)
    invoice = repository.upsert_invoice(
        tenant_id,
        period_id,
        invoice_id_for(period_id),
        datetime.combine(period_end, time.min, tzinfo=UTC),
        subtotal,
        tax,
        total,
        "issued",
        persisted_lines,
    )

    notes = sorted(
        repository.list_credit_notes(tenant_id),
        key=lambda note: (note.issued_on, note.note_id),
    )
    outstanding = credit_applied
    for note in notes:
        if note.remaining_amount <= 0:
            continue
        if outstanding <= 0:
            break
        repository.update_credit_note(
            note.note_id,
            max(note.remaining_amount - outstanding, Decimal("0.00")),
        )
        outstanding = max(outstanding - note.remaining_amount, Decimal("0.00"))
    return invoice, sorted(
        repository.list_credit_notes(tenant_id),
        key=lambda note: (note.issued_on, note.note_id),
    )


def invoice_lines(repository: InvoicingRepository, invoice_id: UUID) -> list[InvoiceLineRow]:
    invoice = repository.get_invoice(invoice_id)
    if invoice is None:
        raise InvoiceNotFoundError("invoice not found")
    return sorted(invoice.lines, key=lambda line: line.line_no)
