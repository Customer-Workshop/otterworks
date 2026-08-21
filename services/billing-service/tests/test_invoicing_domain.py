from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain import (
    CreditNoteRow,
    InvoiceLineRow,
    InvoiceRow,
    PlanRow,
    PreviewLine,
    SubscriptionRow,
    UsageRating,
    credit_note_applications,
    current_subscription,
    invoice_id_for,
    invoice_line_id,
    invoice_lines,
    invoice_preview,
    invoice_totals,
    issue_invoice,
    persisted_line_amount,
    preview_lines,
    rating_period_id,
)

TENANT = UUID("00000000-0000-0000-0000-000000000006")
PLAN_ID = UUID("10000000-0000-0000-0000-000000000002")
SUBSCRIPTION = UUID("20000000-0000-0000-0000-000000000006")
PERIOD_START = date(2026, 2, 1)
PERIOD_END = date(2026, 2, 28)

PLAN = PlanRow(
    plan_id=PLAN_ID,
    code="growth",
    tier=2,
    monthly_fee=Decimal("49.00"),
    included_units=1000,
    overage_rate=Decimal("0.040000"),
    active=True,
)
SUBSCRIPTION_ROW = SubscriptionRow(
    subscription_id=SUBSCRIPTION,
    tenant_id=TENANT,
    plan_id=PLAN_ID,
    starts_on=date(2025, 6, 1),
    ends_on=None,
    status="active",
    suspended_on=None,
)


def rating(overage: str | None) -> UsageRating:
    amount = None if overage is None else Decimal(overage)
    return UsageRating(
        used_units=1139,
        quota_units=1000,
        rollover_units=0,
        billable_units=139,
        first_tier_units=101,
        second_tier_units=38,
        overage_amount=amount,
    )


class FakeInvoicingRepository:
    def __init__(
        self,
        *,
        subscriptions: list[SubscriptionRow] | None = None,
        plan: PlanRow | None = PLAN,
        tax_exempt: bool = False,
        used_units: int = 1139,
        prior_rollover_units: int | None = None,
        credit_notes: list[CreditNoteRow] | None = None,
    ) -> None:
        self.subscriptions = (
            [SUBSCRIPTION_ROW] if subscriptions is None else list(subscriptions)
        )
        self.plan = plan
        self.tax_exempt = tax_exempt
        self.used_units = used_units
        self.prior_rollover_units = prior_rollover_units
        self.credit_notes = list(credit_notes or [])
        self.invoices: list[InvoiceRow] = []
        self.lines: list[InvoiceLineRow] = []
        self.line_ids: list[UUID] = []
        self.rating_periods: list[UUID] = []
        self.rating_results: list[UUID] = []
        self.deleted_lines = 0

    def list_overlapping_subscriptions(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> list[SubscriptionRow]:
        return [
            item
            for item in self.subscriptions
            if item.tenant_id == tenant_id
            and item.starts_on <= period_end
            and (item.ends_on is None or item.ends_on >= period_start)
        ]

    def find_plan(self, plan_id: UUID) -> PlanRow | None:
        return self.plan

    def find_tenant(self, tenant_id: UUID):
        from app.domain import TenantRow

        return TenantRow(tenant_id=tenant_id, tax_exempt=self.tax_exempt)

    def sum_usage_units(self, tenant_id: UUID, period_start: date, period_end: date) -> int:
        return self.used_units

    def sum_prior_rollover_units(
        self, tenant_id: UUID, period_start: date, window_start: date
    ) -> int | None:
        return self.prior_rollover_units

    def sum_open_credit(self, tenant_id: UUID) -> Decimal:
        return sum(
            (note.remaining_amount for note in self.credit_notes if note.remaining_amount > 0),
            Decimal("0"),
        )

    def list_credit_notes(self, tenant_id: UUID) -> list[CreditNoteRow]:
        return list(self.credit_notes)

    def update_credit_note(self, credit_note_id: UUID, remaining_amount: Decimal) -> None:
        self.credit_notes = [
            replace(note, remaining_amount=remaining_amount)
            if note.credit_note_id == credit_note_id
            else note
            for note in self.credit_notes
        ]

    def upsert_rating_period(
        self, period_id: UUID, tenant_id: UUID, period_start: date, period_end: date
    ) -> None:
        self.rating_periods.append(period_id)

    def upsert_rating_result(
        self,
        result_id: UUID,
        period_id: UUID,
        subscription_id: UUID,
        usage_rating: UsageRating,
        rollover_units: int,
        created_on: date,
    ) -> None:
        self.rating_results.append(result_id)

    def upsert_issued_invoice(
        self, invoice_id: UUID, tenant_id: UUID, period_id: UUID, issued_on: date
    ) -> None:
        existing = [item for item in self.invoices if item.invoice_id == invoice_id]
        if existing:
            self.invoices = [
                replace(item, status="issued") if item.invoice_id == invoice_id else item
                for item in self.invoices
            ]
            return
        self.invoices.append(
            InvoiceRow(
                invoice_id=invoice_id,
                tenant_id=tenant_id,
                period_id=period_id,
                subtotal=Decimal("0"),
                tax=Decimal("0"),
                total=Decimal("0"),
                status="issued",
            )
        )

    def update_invoice_totals(
        self, invoice_id: UUID, subtotal: Decimal, tax: Decimal, total: Decimal
    ) -> None:
        self.invoices = [
            replace(item, subtotal=subtotal, tax=tax, total=total)
            if item.invoice_id == invoice_id
            else item
            for item in self.invoices
        ]

    def list_invoices_for_period(self, period_id: UUID) -> list[InvoiceRow]:
        return [item for item in self.invoices if item.period_id == period_id]

    def delete_invoice_lines(self, invoice_id: UUID) -> None:
        self.deleted_lines += 1
        self.lines = []

    def insert_invoice_line(
        self,
        line_id: UUID,
        invoice_id: UUID,
        line_no: int,
        line_type: str,
        description: str | None,
        amount: Decimal | None,
    ) -> None:
        self.line_ids.append(line_id)
        self.lines.append(
            InvoiceLineRow(
                line_no=line_no, line_type=line_type, description=description, amount=amount
            )
        )

    def list_invoice_lines(self, invoice_id: UUID) -> list[InvoiceLineRow]:
        return list(reversed(self.lines))


@pytest.mark.rule("INVOICING-001")
def test_preview_is_five_ordered_lines() -> None:
    lines = preview_lines(PLAN, rating("5.56"), tax_exempt=False, open_credit_total=Decimal("0"))
    assert [line.line_no for line in lines] == [1, 2, 3, 4, 5]
    assert [line.line_type for line in lines] == ["plan", "usage", "tax", "tax", "credit"]
    assert [line.description for line in lines] == [
        "growth",
        "usage overage",
        "regional tax",
        "local tax",
        "credit notes",
    ]


@pytest.mark.rule("INVOICING-002")
def test_plan_and_usage_lines_round_to_two_places() -> None:
    lines = preview_lines(PLAN, rating("5.555"), tax_exempt=True, open_credit_total=Decimal("0"))
    assert lines[0].amount == Decimal("49.00")
    assert lines[0].total == Decimal("49.00")
    assert lines[1].amount == Decimal("5.56")
    assert lines[1].total == Decimal("5.56")


@pytest.mark.rule("INVOICING-002")
def test_latest_subscription_wins_with_id_tiebreak() -> None:
    early = replace(
        SUBSCRIPTION_ROW,
        subscription_id=UUID("20000000-0000-0000-0000-0000000000ff"),
        starts_on=date(2024, 1, 1),
    )
    same_day = replace(
        SUBSCRIPTION_ROW, subscription_id=UUID("20000000-0000-0000-0000-0000000000aa")
    )
    assert current_subscription([early, same_day, SUBSCRIPTION_ROW]) is SUBSCRIPTION_ROW


@pytest.mark.rule("INVOICING-003")
def test_tax_is_split_in_halves_and_waived_for_exempt_tenants() -> None:
    taxed = preview_lines(PLAN, rating("5.56"), False, Decimal("0"))
    assert taxed[2].amount == taxed[3].amount == Decimal("54.56") * Decimal("0.0825") / 2
    assert [line.tax_amount for line in taxed] == [Decimal("0")] * 5

    exempt = preview_lines(PLAN, rating("5.56"), True, Decimal("0"))
    assert exempt[2].amount == exempt[3].amount == Decimal("0")


@pytest.mark.rule("INVOICING-004")
def test_credit_line_is_capped_at_the_gross_amount() -> None:
    capped = preview_lines(PLAN, rating("5.56"), False, Decimal("500.00"))
    assert capped[4].credit_applied == Decimal("59.06")
    assert capped[4].total == Decimal("-59.06")

    partial = preview_lines(PLAN, rating("5.56"), False, Decimal("10.00"))
    assert partial[4].credit_applied == Decimal("10.00")
    assert partial[4].total == Decimal("-10.00")


@pytest.mark.rule("INVOICING-005")
def test_issuing_twice_rebuilds_lines_under_stable_identifiers() -> None:
    repository = FakeInvoicingRepository()
    first = issue_invoice(repository, TENANT, PERIOD_START, PERIOD_END)
    second = issue_invoice(repository, TENANT, PERIOD_START, PERIOD_END)

    period_id = rating_period_id(TENANT, PERIOD_START)
    invoice_id = invoice_id_for(period_id)
    assert repository.rating_periods == [period_id, period_id]
    assert len(repository.invoices) == 1
    assert [line.line_no for line in second.lines] == [1, 2, 3, 4, 5]
    assert first.invoices[0].status == second.invoices[0].status == "issued"
    assert repository.line_ids[:5] == [invoice_line_id(invoice_id, n) for n in range(1, 6)]


@pytest.mark.rule("INVOICING-006")
def test_totals_round_each_tax_half_before_summing() -> None:
    lines = preview_lines(PLAN, rating("0.00"), False, Decimal("0"))
    totals = invoice_totals(lines)
    assert totals.subtotal == Decimal("49.00")
    assert totals.tax == Decimal("4.04")
    assert totals.total == Decimal("53.04")


@pytest.mark.rule("INVOICING-006")
def test_credit_lines_persist_their_negative_total() -> None:
    lines = preview_lines(PLAN, rating("5.56"), False, Decimal("100.00"))
    assert persisted_line_amount(lines[0]) == Decimal("49.00")
    assert persisted_line_amount(lines[4]) == Decimal("-59.06")
    assert invoice_totals(lines).total == Decimal("0.00")


@pytest.mark.rule("INVOICING-007")
def test_credit_notes_are_consumed_in_issued_on_then_id_order() -> None:
    older = CreditNoteRow(
        credit_note_id=UUID("70000000-0000-0000-0000-000000000005"),
        tenant_id=TENANT,
        issued_on=date(2026, 1, 31),
        amount=Decimal("40.00"),
        remaining_amount=Decimal("40.00"),
    )
    newer = CreditNoteRow(
        credit_note_id=UUID("70000000-0000-0000-0000-000000000006"),
        tenant_id=TENANT,
        issued_on=date(2026, 2, 1),
        amount=Decimal("20.00"),
        remaining_amount=Decimal("20.00"),
    )
    applications = credit_note_applications([newer, older], Decimal("53.04"))
    assert applications == [
        (older.credit_note_id, Decimal("0.00")),
        (newer.credit_note_id, Decimal("6.96")),
    ]


@pytest.mark.rule("INVOICING-007")
def test_no_credit_notes_are_touched_without_applied_credit() -> None:
    note = CreditNoteRow(
        credit_note_id=UUID("70000000-0000-0000-0000-000000000005"),
        tenant_id=TENANT,
        issued_on=date(2026, 1, 31),
        amount=Decimal("40.00"),
        remaining_amount=Decimal("40.00"),
    )
    assert credit_note_applications([note], Decimal("0")) == []


@pytest.mark.rule("INVOICING-008")
def test_persisted_lines_are_ordered_by_line_no() -> None:
    repository = FakeInvoicingRepository()
    issue_invoice(repository, TENANT, PERIOD_START, PERIOD_END)
    invoice_id = invoice_id_for(rating_period_id(TENANT, PERIOD_START))
    assert [line.line_no for line in invoice_lines(repository, invoice_id)] == [1, 2, 3, 4, 5]


@pytest.mark.rule("INVOICING-008")
def test_invoice_without_lines_reads_as_an_empty_list() -> None:
    repository = FakeInvoicingRepository()
    assert invoice_lines(repository, invoice_id_for(rating_period_id(TENANT, PERIOD_START))) == []


@pytest.mark.rule("INVOICING-001")
def test_preview_propagates_a_missing_subscription_as_null() -> None:
    repository = FakeInvoicingRepository(subscriptions=[], plan=None)
    lines = invoice_preview(repository, TENANT, PERIOD_START, PERIOD_END)
    assert isinstance(lines[0], PreviewLine)
    assert lines[0].description is None
    assert lines[0].amount is None
    assert lines[2].amount is None
