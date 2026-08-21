from __future__ import annotations

import hashlib
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import UUID, uuid5

PLAN_CHANGE_NAMESPACE = UUID("d8e9df63-6e46-4d6a-b9c2-2ef6e99cb5ee")

ZERO = Decimal("0")
TAX_RATE = Decimal("0.0825")
FIRST_TIER_UNITS = 101
SECOND_TIER_RATE_MULTIPLIER = Decimal("1.5")
ROLLOVER_QUOTA_MULTIPLIER = 2
ROLLOVER_WINDOW_MONTHS = 3


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
class TenantRow:
    tenant_id: UUID
    tax_exempt: bool


@dataclass(frozen=True)
class CreditNoteRow:
    credit_note_id: UUID
    tenant_id: UUID
    issued_on: date
    amount: Decimal
    remaining_amount: Decimal


@dataclass(frozen=True)
class InvoiceRow:
    invoice_id: UUID
    tenant_id: UUID
    period_id: UUID
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: str


@dataclass(frozen=True)
class InvoiceLineRow:
    line_no: int
    line_type: str
    description: str | None
    amount: Decimal | None


@dataclass(frozen=True)
class UsageRating:
    used_units: int
    quota_units: int | None
    rollover_units: int | None
    billable_units: int | None
    first_tier_units: int | None
    second_tier_units: int | None
    overage_amount: Decimal | None


@dataclass(frozen=True)
class PreviewLine:
    line_no: int
    line_type: str
    description: str | None
    amount: Decimal | None
    tax_amount: Decimal
    credit_applied: Decimal | None
    total: Decimal | None


@dataclass(frozen=True)
class InvoiceTotals:
    subtotal: Decimal | None
    tax: Decimal | None
    credit: Decimal | None
    total: Decimal | None


@dataclass(frozen=True)
class IssuedInvoice:
    invoices: list[InvoiceRow]
    credit_notes: list[CreditNoteRow]
    lines: list[InvoiceLineRow]


class InvoicingRepository(Protocol):
    def list_overlapping_subscriptions(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> list[SubscriptionRow]: ...

    def find_plan(self, plan_id: UUID) -> PlanRow | None: ...

    def find_tenant(self, tenant_id: UUID) -> TenantRow | None: ...

    def sum_usage_units(self, tenant_id: UUID, period_start: date, period_end: date) -> int: ...

    def sum_prior_rollover_units(
        self, tenant_id: UUID, period_start: date, window_start: date
    ) -> int | None: ...

    def sum_open_credit(self, tenant_id: UUID) -> Decimal: ...

    def list_credit_notes(self, tenant_id: UUID) -> list[CreditNoteRow]: ...

    def update_credit_note(self, credit_note_id: UUID, remaining_amount: Decimal) -> None: ...

    def upsert_rating_period(
        self, period_id: UUID, tenant_id: UUID, period_start: date, period_end: date
    ) -> None: ...

    def upsert_rating_result(
        self,
        result_id: UUID,
        period_id: UUID,
        subscription_id: UUID,
        rating: UsageRating,
        rollover_units: int,
        created_on: date,
    ) -> None: ...

    def upsert_issued_invoice(
        self, invoice_id: UUID, tenant_id: UUID, period_id: UUID, issued_on: date
    ) -> None: ...

    def update_invoice_totals(
        self, invoice_id: UUID, subtotal: Decimal, tax: Decimal, total: Decimal
    ) -> None: ...

    def list_invoices_for_period(self, period_id: UUID) -> list[InvoiceRow]: ...

    def delete_invoice_lines(self, invoice_id: UUID) -> None: ...

    def insert_invoice_line(
        self,
        line_id: UUID,
        invoice_id: UUID,
        line_no: int,
        line_type: str,
        description: str | None,
        amount: Decimal | None,
    ) -> None: ...

    def list_invoice_lines(self, invoice_id: UUID) -> list[InvoiceLineRow]: ...


def sql_round(value: Decimal | None, digits: int = 0) -> Decimal | None:
    """round() on numeric: half away from zero, NULL in NULL out."""
    if value is None:
        return None
    return value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def sql_least(*values: Decimal | int | None) -> Decimal | int | None:
    """LEAST(): NULL arguments are ignored, all-NULL yields NULL."""
    present = [value for value in values if value is not None]
    return min(present) if present else None


def sql_greatest(*values: Decimal | int | None) -> Decimal | int | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _subtract(left: Decimal | int | None, right: Decimal | int | None) -> Decimal | int | None:
    return None if left is None or right is None else left - right


def _add(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left + right


def _multiply(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left * right


def md5_uuid(text: str) -> UUID:
    """md5(text)::uuid, the identifier derivation the procedures use."""
    return UUID(hashlib.md5(text.encode(), usedforsecurity=False).hexdigest())


def rating_period_id(tenant_id: UUID, period_start: date) -> UUID:
    return md5_uuid(f"{tenant_id}{period_start.isoformat()}")


def invoice_id_for(period_id: UUID) -> UUID:
    return md5_uuid(f"{period_id}invoice")


def invoice_line_id(invoice_id: UUID, line_no: int) -> UUID:
    return md5_uuid(f"{invoice_id}{line_no}")


def rating_result_id(period_id: UUID) -> UUID:
    return md5_uuid(str(period_id))


def rollover_window_start(period_start: date) -> date:
    """period_start - interval '3 months', clamped to the shorter month."""
    month = period_start.month - ROLLOVER_WINDOW_MONTHS
    year = period_start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, min(period_start.day, monthrange(year, month)[1]))


def current_subscription(subscriptions: list[SubscriptionRow]) -> SubscriptionRow | None:
    """ORDER BY starts_on DESC LIMIT 1, with the id as the explicit tiebreaker."""
    if not subscriptions:
        return None
    latest = max(subscription.starts_on for subscription in subscriptions)
    return min(
        (item for item in subscriptions if item.starts_on == latest),
        key=lambda item: item.subscription_id,
    )


def overlapping(
    subscriptions: list[SubscriptionRow], period_start: date, period_end: date
) -> list[SubscriptionRow]:
    return [
        item
        for item in subscriptions
        if item.starts_on <= period_end and (item.ends_on is None or item.ends_on >= period_start)
    ]


def rate_usage(
    plan: PlanRow | None,
    subscription: SubscriptionRow | None,
    used_units: int,
    prior_rollover_units: int | None,
    period_start: date,
    period_end: date,
) -> UsageRating:
    """billing.fn_usage_rating, reproduced for invoicing."""
    included = plan.included_units if plan is not None else None
    quota_cap = None if included is None else ROLLOVER_QUOTA_MULTIPLIER * included
    prior = sql_least(quota_cap, prior_rollover_units or 0)
    prior = None if prior is None else int(prior)
    rollover = sql_least(prior, quota_cap)
    billable = sql_greatest(_subtract(_subtract(used_units, rollover), included), 0)
    first = sql_least(billable, FIRST_TIER_UNITS)
    second = sql_greatest(_subtract(billable, FIRST_TIER_UNITS), 0)
    rate = plan.overage_rate if plan is not None else None
    amount = sql_round(
        _add(
            _multiply(None if first is None else Decimal(first), rate),
            _multiply(
                _multiply(None if second is None else Decimal(second), rate),
                SECOND_TIER_RATE_MULTIPLIER,
            ),
        ),
        2,
    )
    if (
        subscription is not None
        and subscription.status == "suspended"
        and subscription.suspended_on is not None
        and period_start <= subscription.suspended_on <= period_end
    ):
        factor = Decimal((period_end - subscription.suspended_on).days + 1) / Decimal(
            (period_end - period_start).days + 1
        )
        rounded = sql_round(_multiply(None if billable is None else Decimal(billable), factor))
        billable = None if rounded is None else int(rounded)
        amount = sql_round(_multiply(amount, factor), 2)
    return UsageRating(
        used_units=used_units,
        quota_units=included,
        rollover_units=rollover,
        billable_units=billable,
        first_tier_units=first,
        second_tier_units=second,
        overage_amount=amount,
    )


def preview_lines(
    plan: PlanRow | None,
    rating: UsageRating,
    tax_exempt: bool | None,
    open_credit_total: Decimal,
) -> list[PreviewLine]:
    """The five ordered preview lines of billing.fn_invoice_preview."""
    fee = plan.monthly_fee if plan is not None else None
    overage = rating.overage_amount
    tax = ZERO if tax_exempt else _multiply(_add(fee, overage), TAX_RATE)
    half_tax = None if tax is None else tax / 2
    applied = sql_least(open_credit_total, sql_round(_add(_add(fee, overage), tax), 2))
    return [
        PreviewLine(1, "plan", plan.code if plan else None, sql_round(fee, 2), ZERO, ZERO,
                    sql_round(fee, 2)),
        PreviewLine(2, "usage", "usage overage", sql_round(overage, 2), ZERO, ZERO,
                    sql_round(overage, 2)),
        PreviewLine(3, "tax", "regional tax", half_tax, ZERO, ZERO, half_tax),
        PreviewLine(4, "tax", "local tax", half_tax, ZERO, ZERO, half_tax),
        PreviewLine(5, "credit", "credit notes", ZERO, ZERO, applied, _subtract(ZERO, applied)),
    ]


def persisted_line_amount(line: PreviewLine) -> Decimal | None:
    return line.total if line.line_type == "credit" else line.amount


def invoice_totals(lines: list[PreviewLine]) -> InvoiceTotals:
    """Subtotal and tax accumulate per-line rounded amounts; credit is the applied amount."""
    subtotal: Decimal | None = ZERO
    tax: Decimal | None = ZERO
    credit: Decimal | None = ZERO
    for line in lines:
        if line.line_type in {"plan", "usage"}:
            subtotal = _add(subtotal, sql_round(line.amount, 2))
        elif line.line_type == "tax":
            tax = _add(tax, sql_round(line.amount, 2))
        elif line.line_type == "credit":
            credit = line.credit_applied
    return InvoiceTotals(
        subtotal=sql_round(subtotal, 2),
        tax=sql_round(tax, 2),
        credit=credit,
        total=sql_round(_subtract(_add(subtotal, tax), credit), 2),
    )


def credit_note_applications(
    notes: list[CreditNoteRow], credit: Decimal | None
) -> list[tuple[UUID, Decimal]]:
    """Consume open credit notes in issued_on, id order until the applied credit is exhausted."""
    applications: list[tuple[UUID, Decimal]] = []
    remaining_credit = credit
    for note in sorted(
        (item for item in notes if item.remaining_amount > 0),
        key=lambda item: (item.issued_on, item.credit_note_id),
    ):
        if remaining_credit is None or remaining_credit <= 0:
            break
        applications.append(
            (note.credit_note_id, sql_greatest(note.remaining_amount - remaining_credit, ZERO))
        )
        remaining_credit = sql_greatest(remaining_credit - note.remaining_amount, ZERO)
    return applications


def usage_rating_for(
    repository: InvoicingRepository, tenant_id: UUID, period_start: date, period_end: date
) -> tuple[PlanRow | None, SubscriptionRow | None, UsageRating]:
    subscription = current_subscription(
        repository.list_overlapping_subscriptions(tenant_id, period_start, period_end)
    )
    plan = None if subscription is None else repository.find_plan(subscription.plan_id)
    used = repository.sum_usage_units(tenant_id, period_start, period_end)
    prior = repository.sum_prior_rollover_units(
        tenant_id, period_start, rollover_window_start(period_start)
    )
    return plan, subscription, rate_usage(plan, subscription, used, prior, period_start, period_end)


def invoice_preview(
    repository: InvoicingRepository, tenant_id: UUID, period_start: date, period_end: date
) -> list[PreviewLine]:
    plan, _subscription, rating = usage_rating_for(
        repository, tenant_id, period_start, period_end
    )
    tenant = repository.find_tenant(tenant_id)
    return preview_lines(
        plan,
        rating,
        tenant.tax_exempt if tenant is not None else None,
        repository.sum_open_credit(tenant_id),
    )


def finalize_rating(
    repository: InvoicingRepository, tenant_id: UUID, period_start: date, period_end: date
) -> None:
    """billing.sp_finalize_rating, reproduced so issuing an invoice is self-contained."""
    period_id = rating_period_id(tenant_id, period_start)
    subscription = current_subscription(
        repository.list_overlapping_subscriptions(tenant_id, period_start, period_end)
    )
    repository.upsert_rating_period(period_id, tenant_id, period_start, period_end)
    _plan, _subscription, rating = usage_rating_for(
        repository, tenant_id, period_start, period_end
    )
    if subscription is None:
        return
    repository.upsert_rating_result(
        rating_result_id(period_id),
        period_id,
        subscription.subscription_id,
        rating,
        int(sql_greatest(_subtract(rating.quota_units, rating.used_units), 0) or 0),
        period_end,
    )


def issue_invoice(
    repository: InvoicingRepository, tenant_id: UUID, period_start: date, period_end: date
) -> IssuedInvoice:
    """billing.sp_issue_invoice."""
    finalize_rating(repository, tenant_id, period_start, period_end)
    period_id = rating_period_id(tenant_id, period_start)
    invoice_id = invoice_id_for(period_id)
    repository.upsert_issued_invoice(invoice_id, tenant_id, period_id, period_end)
    repository.delete_invoice_lines(invoice_id)
    lines = invoice_preview(repository, tenant_id, period_start, period_end)
    for line in lines:
        repository.insert_invoice_line(
            invoice_line_id(invoice_id, line.line_no),
            invoice_id,
            line.line_no,
            line.line_type,
            line.description,
            persisted_line_amount(line),
        )
    totals = invoice_totals(lines)
    repository.update_invoice_totals(invoice_id, totals.subtotal, totals.tax, totals.total)
    for credit_note_id, remaining in credit_note_applications(
        repository.list_credit_notes(tenant_id), totals.credit
    ):
        repository.update_credit_note(credit_note_id, remaining)
    return IssuedInvoice(
        invoices=repository.list_invoices_for_period(period_id),
        credit_notes=sorted(
            repository.list_credit_notes(tenant_id),
            key=lambda item: (item.issued_on, item.credit_note_id),
        ),
        lines=invoice_lines(repository, invoice_id),
    )


def invoice_lines(repository: InvoicingRepository, invoice_id: UUID) -> list[InvoiceLineRow]:
    """billing.fn_invoice_lines: persisted lines ordered by line_no."""
    return sorted(repository.list_invoice_lines(invoice_id), key=lambda line: line.line_no)
