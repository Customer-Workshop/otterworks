"""Application-side replacement for the Oracle PKG_INVOICING package."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable

from bson import Decimal128

from tp_mongo.rating_service import (
    NS_VALUE,
    TARGET_DB,
    MongoSubscriptionSource,
    _date_for_compare,
    _round_decimal,
    _utc_ms,
    md5_uuid,
)

TAX_RATE = Decimal("0.0825")
NS_FILTER = {"ns": NS_VALUE}


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    to_decimal = getattr(value, "to_decimal", None)
    if callable(to_decimal):
        value = to_decimal()
    return Decimal(str(value))


def _date(value: date | datetime) -> date:
    return _date_for_compare(value)


def _add(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left + right


def _subtract(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    return None if left is None or right is None else left - right


def _mongo_decimal(value: Decimal | None) -> Decimal128 | None:
    return None if value is None else Decimal128(value)


class InvoicingService:
    """Invoicing operations restricted to the U5 target database."""

    def __init__(self, db, rating_service, audit_sink: Callable | None = None):
        if db.name != TARGET_DB:
            raise ValueError(
                f"invoicing service is restricted to {TARGET_DB}: got {db.name}"
            )
        self.db = db
        self.invoices = db["invoices"]
        self.credit_notes = db["credit_notes"]
        self.tenants = db["tenants"]
        self.plans = db["plans"]
        self.subscription_source = getattr(
            rating_service, "subscription_source", MongoSubscriptionSource(db)
        )
        self.rating_service = rating_service
        self.audit_sink = audit_sink or (lambda _module, _message: None)

    def _plan(self, tenant_id, period_start, period_end, session=None):
        subscription = self.subscription_source.latest_covering(
            tenant_id, period_start, period_end, session=session
        )
        if not subscription or not subscription.get("plan_id"):
            return None
        return self.plans.find_one(
            {"_id": subscription["plan_id"], **NS_FILTER}, session=session
        )

    def compute_preview(self, tenant_id, period_start, period_end, session=None):
        plan = self._plan(tenant_id, period_start, period_end, session=session)
        plan_code = plan.get("code") if plan else None
        plan_fee = _decimal(plan.get("monthly_fee")) if plan else None
        rating = self.rating_service.compute_rating(
            tenant_id, period_start, period_end, session=session
        )
        overage = _decimal(rating.overage_amount)
        credit = Decimal("0")
        for note in self.credit_notes.find(
            {"tenant_id": tenant_id, **NS_FILTER}, session=session
        ):
            remaining = _decimal(note.get("remaining_amount"))
            if remaining is not None and remaining > 0:
                credit += remaining

        tenant = self.tenants.find_one({"_id": tenant_id, **NS_FILTER}, session=session)
        exempt = (tenant or {}).get("tax_exempt_yn") or "N"
        tax = (
            Decimal("0")
            if exempt == "Y"
            else (
                None
                if plan_fee is None or overage is None
                else (plan_fee + overage) * TAX_RATE
            )
        )
        return {
            "plan_code": plan_code,
            "plan_fee": plan_fee,
            "overage": overage,
            "credit": credit,
            "tax": tax,
        }

    def invoice_preview(self, tenant_id, period_start, period_end, session=None):
        preview = self.compute_preview(
            tenant_id, period_start, period_end, session=session
        )
        plan_fee = preview["plan_fee"]
        overage = preview["overage"]
        tax = preview["tax"]
        charge_cap = (
            None
            if plan_fee is None or overage is None or tax is None
            else _round_decimal(plan_fee + overage + tax, 2)
        )
        credit = preview["credit"]
        credit_applied = min(credit, charge_cap if charge_cap is not None else credit)
        return [
            {
                "line_no": 1,
                "line_type": "plan",
                "description": preview["plan_code"],
                "amount": None if plan_fee is None else _round_decimal(plan_fee, 2),
                "tax_amount": Decimal("0"),
                "credit_applied": Decimal("0"),
                "total": None if plan_fee is None else _round_decimal(plan_fee, 2),
            },
            {
                "line_no": 2,
                "line_type": "usage",
                "description": "usage overage",
                "amount": None if overage is None else _round_decimal(overage, 2),
                "tax_amount": Decimal("0"),
                "credit_applied": Decimal("0"),
                "total": None if overage is None else _round_decimal(overage, 2),
            },
            {
                "line_no": 3,
                "line_type": "tax",
                "description": "regional tax",
                "amount": None if tax is None else tax / 2,
                "tax_amount": Decimal("0"),
                "credit_applied": Decimal("0"),
                "total": None if tax is None else tax / 2,
            },
            {
                "line_no": 4,
                "line_type": "tax",
                "description": "local tax",
                "amount": None if tax is None else tax / 2,
                "tax_amount": Decimal("0"),
                "credit_applied": Decimal("0"),
                "total": None if tax is None else tax / 2,
            },
            {
                "line_no": 5,
                "line_type": "credit",
                "description": "credit notes",
                "amount": Decimal("0"),
                "tax_amount": Decimal("0"),
                "credit_applied": credit_applied,
                "total": -credit_applied,
            },
        ]

    def invoice_lines(self, invoice_id):
        invoice = self.invoices.find_one({"_id": invoice_id, **NS_FILTER})
        if not invoice:
            return []
        return [
            {
                "line_no": line.get("line_no"),
                "line_type": line.get("line_type"),
                "description": line.get("description"),
                "amount": _decimal(line.get("amount")),
            }
            for line in sorted(invoice.get("lines", []), key=lambda line: line.get("line_no"))
        ]

    def issue_invoice(self, tenant_id, period_start, period_end):
        period_id = md5_uuid(tenant_id + _date(period_start).strftime("%Y-%m-%d"))
        invoice_id = md5_uuid(period_id + "invoice")
        self.rating_service.finalize_rating(tenant_id, period_start, period_end)

        with self.db.client.start_session() as session:
            with session.start_transaction():
                existing = self.invoices.find_one(
                    {"_id": invoice_id, **NS_FILTER}, session=session
                )
                if existing is None:
                    self.invoices.insert_one(
                        {
                            "_id": invoice_id,
                            "tenant_id": tenant_id,
                            "period_id": period_id,
                            "issued_at": _utc_ms(_date(period_end)),
                            "subtotal": Decimal128("0.00"),
                            "tax": Decimal128("0.00"),
                            "total": Decimal128("0.00"),
                            "status_cd": 20,
                            "ns": NS_VALUE,
                        },
                        session=session,
                    )
                else:
                    self.invoices.update_one(
                        {"_id": invoice_id, **NS_FILTER},
                        {"$set": {"status_cd": 20}},
                        session=session,
                    )

                lines = []
                subtotal = Decimal("0")
                tax_total = Decimal("0")
                credit_applied = Decimal("0")
                for row in self.invoice_preview(
                    tenant_id, period_start, period_end, session=session
                ):
                    amount = row["total"] if row["line_type"] == "credit" else row["amount"]
                    lines.append(
                        {
                            "line_no": row["line_no"],
                            "id": md5_uuid(invoice_id + str(row["line_no"])),
                            "line_type": row["line_type"],
                            "description": row["description"],
                            "amount": _mongo_decimal(amount),
                        }
                    )
                    if row["line_type"] in ("plan", "usage"):
                        subtotal = (
                            None
                            if subtotal is None or amount is None
                            else subtotal + _round_decimal(amount, 2)
                        )
                    elif row["line_type"] == "tax":
                        tax_total = (
                            None
                            if tax_total is None or amount is None
                            else tax_total + _round_decimal(amount, 2)
                        )
                    elif row["line_type"] == "credit":
                        credit_applied = row["credit_applied"]

                subtotal_and_tax = _add(subtotal, tax_total)
                total_before_rounding = _subtract(subtotal_and_tax, credit_applied)
                total = (
                    None
                    if total_before_rounding is None
                    else _round_decimal(total_before_rounding, 2)
                )
                self.invoices.update_one(
                    {"_id": invoice_id, **NS_FILTER},
                    {
                        "$set": {
                            "lines": lines,
                            "subtotal": _mongo_decimal(
                                None if subtotal is None else _round_decimal(subtotal, 2)
                            ),
                            "tax": _mongo_decimal(
                                None if tax_total is None else _round_decimal(tax_total, 2)
                            ),
                            "total": _mongo_decimal(total),
                        }
                    },
                    session=session,
                )

                running = credit_applied
                notes = self.credit_notes.find(
                    {"tenant_id": tenant_id, **NS_FILTER}, session=session
                ).sort([("issued_on", 1), ("_id", 1)])
                for note in notes:
                    old_remaining = _decimal(note.get("remaining_amount"))
                    if old_remaining is None or old_remaining <= 0:
                        continue
                    if running <= 0:
                        break
                    new_remaining = max(old_remaining - running, Decimal("0"))
                    self.credit_notes.update_one(
                        {"_id": note["_id"], **NS_FILTER},
                        {"$set": {"remaining_amount": _mongo_decimal(new_remaining)}},
                        session=session,
                    )
                    running = max(running - old_remaining, Decimal("0"))

        self.audit_sink(
            "INVOICING",
            f"issued invoice={invoice_id} total={total if total is not None else Decimal('0')}",
        )
        return self.invoices.find_one({"_id": invoice_id, **NS_FILTER})
