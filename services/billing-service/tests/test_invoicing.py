from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain import PlanRow, SubscriptionRow
from app.invoicing import (
    CreditNoteRow,
    CustomerRow,
    InvoiceLineRow,
    InvoiceNotFoundError,
    InvoiceRow,
    invoice_id_for,
    invoice_lines,
    issue,
    preview,
)
from app.rating import RatingPeriodRow, RatingResultRow, UsageEventRow, period_id_for

TENANT = UUID("00000000-0000-0000-0000-000000000006")
PLAN = UUID("10000000-0000-0000-0000-000000000001")
GROWTH = UUID("10000000-0000-0000-0000-000000000002")
SUBSCRIPTION = UUID("20000000-0000-0000-0000-000000000006")
PERIOD = date(2026, 2, 1)
END = date(2026, 2, 28)


@dataclass
class FakeRepository:
    customers: list[CustomerRow]
    plans: list[PlanRow]
    subscriptions: list[SubscriptionRow]
    events: list[UsageEventRow]
    periods: list[RatingPeriodRow]
    credit_notes: list[CreditNoteRow]
    invoices: list[InvoiceRow]
    rating_upserts: list[RatingPeriodRow]
    invoice_upserts: list[InvoiceRow]

    def get_customer(self, tenant_id: UUID) -> CustomerRow | None:
        return next((item for item in self.customers if item.tenant_id == tenant_id), None)

    def get_plan(self, plan_id: UUID) -> PlanRow | None:
        return next((item for item in self.plans if item.plan_id == plan_id), None)

    def list_subscriptions(self, tenant_id: UUID) -> list[SubscriptionRow]:
        return [item for item in self.subscriptions if item.tenant_id == tenant_id]

    def list_usage_events(self, tenant_id: UUID) -> list[UsageEventRow]:
        return [item for item in self.events if item.tenant_id == tenant_id]

    def list_rating_periods(self, tenant_id: UUID) -> list[RatingPeriodRow]:
        return [item for item in self.periods if item.tenant_id == tenant_id]

    def upsert_rating_period(
        self,
        tenant_id: UUID,
        period_start: date,
        period_end: date,
        period_id: UUID,
        result: RatingResultRow,
    ) -> RatingPeriodRow:
        row = RatingPeriodRow(period_id, tenant_id, period_start, period_end, result)
        self.rating_upserts.append(row)
        self.periods = [
            item
            for item in self.periods
            if not (item.tenant_id == tenant_id and item.period_start == period_start)
        ]
        self.periods.append(row)
        return row

    def list_credit_notes(self, tenant_id: UUID) -> list[CreditNoteRow]:
        return [item for item in self.credit_notes if item.tenant_id == tenant_id]

    def get_invoice(self, invoice_id: UUID) -> InvoiceRow | None:
        return next((item for item in self.invoices if item.invoice_id == invoice_id), None)

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
    ) -> InvoiceRow:
        existing = next(
            (
                item
                for item in self.invoices
                if item.tenant_id == tenant_id and item.period_id == period_id
            ),
            None,
        )
        stored_id = existing.invoice_id if existing is not None else invoice_id
        row = InvoiceRow(
            stored_id,
            tenant_id,
            period_id,
            issued_at,
            subtotal,
            tax,
            total,
            status,
            lines,
        )
        self.invoice_upserts.append(row)
        self.invoices = [
            item
            for item in self.invoices
            if not (item.tenant_id == tenant_id and item.period_id == period_id)
        ]
        self.invoices.append(row)
        return row

    def update_credit_note(self, note_id: UUID, remaining_amount: Decimal) -> None:
        self.credit_notes = [
            CreditNoteRow(
                item.note_id,
                item.tenant_id,
                item.issued_on,
                item.amount,
                remaining_amount,
            )
            if item.note_id == note_id
            else item
            for item in self.credit_notes
        ]


def repository(
    *,
    tax_exempt: bool = False,
    used_units: int = 201,
    periods: list[RatingPeriodRow] | None = None,
    credit_notes: list[CreditNoteRow] | None = None,
    invoices: list[InvoiceRow] | None = None,
) -> FakeRepository:
    return FakeRepository(
        customers=[CustomerRow(TENANT, "Tenant Six", tax_exempt, "active")],
        plans=[
            PlanRow(
                PLAN,
                "STARTER",
                "starter",
                Decimal("49.00"),
                100,
                Decimal("0.055"),
                True,
            )
        ],
        subscriptions=[
            SubscriptionRow(
                SUBSCRIPTION,
                TENANT,
                PLAN,
                date(2026, 1, 1),
                None,
                "active",
                None,
            )
        ],
        events=[
            UsageEventRow(
                UUID("30000000-0000-0000-0000-000000000006"),
                TENANT,
                datetime(2026, 2, 10, tzinfo=UTC),
                used_units,
                "api",
            )
        ],
        periods=periods or [],
        credit_notes=credit_notes or [],
        invoices=invoices or [],
        rating_upserts=[],
        invoice_upserts=[],
    )


@pytest.mark.rule("INVOICE-R001")
def test_preview_uses_latest_overlapping_subscription_plan() -> None:
    repo = repository()
    repo.plans.append(
        PlanRow(GROWTH, "GROWTH", "growth", Decimal("149.00"), 500, Decimal("0.035"), True)
    )
    repo.subscriptions.append(
        SubscriptionRow(
            UUID("20000000-0000-0000-0000-000000000007"),
            TENANT,
            GROWTH,
            date(2026, 2, 1),
            None,
            "active",
            None,
        )
    )
    assert preview(repo, TENANT, PERIOD, END)[0].amount == Decimal("149.00")


@pytest.mark.rule("INVOICE-R002")
def test_preview_usage_line_reuses_rating_overage() -> None:
    assert preview(repository(), TENANT, PERIOD, END)[1].amount == Decimal("5.56")


@pytest.mark.rule("INVOICE-R003")
def test_preview_sums_open_credit_notes() -> None:
    notes = [
        CreditNoteRow(
            UUID("70000000-0000-0000-0000-000000000005"),
            TENANT,
            date(2026, 1, 31),
            Decimal("5.00"),
            Decimal("5.00"),
        ),
        CreditNoteRow(
            UUID("70000000-0000-0000-0000-000000000006"),
            TENANT,
            date(2026, 2, 1),
            Decimal("55.00"),
            Decimal("55.00"),
        ),
    ]
    credit_line = preview(repository(used_units=100, credit_notes=notes), TENANT, PERIOD, END)[4]
    assert credit_line.credit_applied == Decimal("53.04")


@pytest.mark.rule("INVOICE-R004")
def test_preview_applies_tax_exemption_and_regional_rate() -> None:
    taxable = preview(repository(), TENANT, PERIOD, END)
    exempt = preview(repository(tax_exempt=True), TENANT, PERIOD, END)
    assert taxable[2].amount == Decimal("2.2506")
    assert exempt[2].amount == Decimal("0.00")


@pytest.mark.rule("INVOICE-R005")
def test_preview_has_five_fixed_lines_and_zero_tax_amount_columns() -> None:
    lines = preview(repository(), TENANT, PERIOD, END)
    assert [line.line_type for line in lines] == ["plan", "usage", "tax", "tax", "credit"]
    assert all(line.tax_amount == Decimal("0.00") for line in lines)
    assert lines[2].amount == lines[3].amount == Decimal("2.2506")


@pytest.mark.rule("INVOICE-R006")
def test_preview_caps_credit_at_gross_and_keeps_zero_total_positive() -> None:
    no_credit = preview(repository(), TENANT, PERIOD, END)[4]
    assert no_credit.credit_applied == Decimal("0.00")
    assert no_credit.total == Decimal("0.00")


@pytest.mark.rule("INVOICE-R007")
def test_invoice_lines_are_ordered_by_line_number() -> None:
    invoice = InvoiceRow(
        UUID("60000000-0000-0000-0000-000000000006"),
        TENANT,
        UUID("40000000-0000-0000-0000-000000000006"),
        datetime(2026, 2, 28, tzinfo=UTC),
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.00"),
        "issued",
        [
            InvoiceLineRow(2, "usage", "usage overage", Decimal("12.29")),
            InvoiceLineRow(1, "plan", "GROWTH", Decimal("149.00")),
        ],
    )
    repo = repository(invoices=[invoice])
    assert [line.line_no for line in invoice_lines(repo, invoice.invoice_id)] == [1, 2]


@pytest.mark.rule("INVOICE-R008")
def test_issue_finalizes_rating_and_marks_invoice_issued() -> None:
    period_id = period_id_for(TENANT, PERIOD)
    existing = InvoiceRow(
        UUID("60000000-0000-0000-0000-000000000099"),
        TENANT,
        period_id,
        datetime(2026, 2, 1, tzinfo=UTC),
        Decimal("1.00"),
        Decimal("1.00"),
        Decimal("1.00"),
        "overdue",
        [],
    )
    repo = repository(invoices=[existing])
    invoice, _ = issue(repo, TENANT, PERIOD, END)
    assert invoice.status == "issued"
    assert invoice.invoice_id == existing.invoice_id
    assert invoice.period_id == period_id
    assert len(repo.rating_upserts) == 1
    assert len(repo.invoices) == 1


@pytest.mark.rule("INVOICE-R009")
def test_issue_persists_credit_total_as_signed_line_amount() -> None:
    note = CreditNoteRow(
        UUID("70000000-0000-0000-0000-000000000006"),
        TENANT,
        date(2026, 2, 1),
        Decimal("55.00"),
        Decimal("55.00"),
    )
    invoice, _ = issue(repository(used_units=100, credit_notes=[note]), TENANT, PERIOD, END)
    assert invoice.lines[-1].amount == Decimal("-53.04")
    assert invoice.lines[0].amount == Decimal("49.00")


@pytest.mark.rule("INVOICE-R010")
def test_issue_rounds_tax_lines_before_summing_invoice_tax() -> None:
    invoice, _ = issue(repository(), TENANT, PERIOD, END)
    assert invoice.subtotal == Decimal("54.56")
    assert invoice.tax == Decimal("4.50")
    assert invoice.total == Decimal("59.06")


@pytest.mark.rule("INVOICE-R011")
def test_issue_draws_credit_notes_down_using_original_balances() -> None:
    notes = [
        CreditNoteRow(
            UUID("70000000-0000-0000-0000-000000000005"),
            TENANT,
            date(2026, 1, 31),
            Decimal("5.00"),
            Decimal("5.00"),
        ),
        CreditNoteRow(
            UUID("70000000-0000-0000-0000-000000000006"),
            TENANT,
            date(2026, 2, 1),
            Decimal("55.00"),
            Decimal("55.00"),
        ),
    ]
    _, updated = issue(repository(used_units=100, credit_notes=notes), TENANT, PERIOD, END)
    assert [note.remaining_amount for note in updated] == [Decimal("0.00"), Decimal("6.96")]


@pytest.mark.rule("INVOICE-R012")
def test_invoice_rejects_missing_plan_subscription_or_invoice() -> None:
    repo = repository()
    repo.subscriptions = []
    with pytest.raises(InvoiceNotFoundError):
        preview(repo, TENANT, PERIOD, END)

    repo = repository()
    repo.plans = []
    with pytest.raises(InvoiceNotFoundError):
        preview(repo, TENANT, PERIOD, END)

    with pytest.raises(InvoiceNotFoundError):
        invoice_lines(repo, invoice_id_for(UUID("40000000-0000-0000-0000-000000000006")))
