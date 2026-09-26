"""Unit invoicing: INVOICES(+lines[]) / CREDIT_NOTES (wave 1).

Ports (db/oracle/packages/04_pkg_invoicing.sql, facade.py):
- pkg_invoicing.compute_preview    -> compute_preview(): package globals -> a Preview value
- pkg_invoicing.fn_invoice_preview -> invoice_preview(): the 5 preview lines
- pkg_invoicing.fn_invoice_lines   -> invoice_lines(): read invoices.lines[] ordered by lineNo
- pkg_invoicing.sp_issue_invoice   -> issue_invoice(): finalize rating, then ONE replace-upsert of
                                      the invoice document with header totals and lines[] rebuilt
                                      (the DELETE lines + INSERT header + INSERT lines + UPDATE
                                      totals sequence collapses into a single document write),
                                      then the oldest-first credit-note burn-down
- facade GET /invoices             -> list_invoices(): invoices x rating_periods x codes(INV_STATUS)

Reads tenants/plans/codes (wave-0) and subscriptions/usage/rating (subscriptions_rating unit)
read-only through that unit's module. Writes only invoices, credit_notes (and rating_periods via
subscriptions_rating.finalize_rating, as the PL/SQL did).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from pymongo import ASCENDING, DESCENDING

from . import db
from . import shared_reference
from . import subscriptions_rating as rating
from ._util import dec, md5_uuid, money, num_out, oround, strip_none, trunc, ymd

TAX_RATE = Decimal("0.0825")  # hardcoded 2011 combined rate (pkg_invoicing)
INV_STATUS_ISSUED = 20


@dataclass
class Preview:
    """pkg_invoicing g_* globals as a request-scoped value."""
    plan_code: Optional[str] = None
    plan_fee: Optional[Decimal] = None
    overage: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    credit: Decimal = Decimal(0)


def compute_preview(tenant_id, period_start, period_end):
    p = Preview()
    sub = rating.covering_subscription(tenant_id, period_start, period_end)
    if sub is not None and sub.get("planId"):
        plan = db().plans.find_one({"_id": sub["planId"]})
        if plan:  # inner join subscriptions x plans
            p.plan_code = plan.get("code")
            p.plan_fee = dec(plan.get("monthlyFee"))

    p.overage = rating.compute_rating(tenant_id, period_start, period_end).overage_amount

    agg = list(db().credit_notes.aggregate([
        {"$match": {"tenantId": tenant_id, "remainingAmount": {"$gt": 0}}},
        {"$group": {"_id": None, "credit": {"$sum": "$remainingAmount"}}},
    ]))
    p.credit = dec(agg[0]["credit"]) if agg else Decimal(0)

    tenant = db().tenants.find_one({"_id": tenant_id}, {"taxExemptYn": 1}) or {}
    exempt = tenant.get("taxExemptYn") is True  # NVL(tax_exempt_yn,'N')
    if exempt:
        p.tax = Decimal(0)
    elif p.plan_fee is None or p.overage is None:
        p.tax = None  # NULL propagates, like the original
    else:
        p.tax = (p.plan_fee + p.overage) * TAX_RATE
    return p


def _half(value):
    return None if value is None else value / 2


def _neg(value):
    return None if value is None else -value


def _preview_lines(p):
    """fn_invoice_preview's UNION ALL, as rows (line_no, line_type, description, amount,
    tax_amount, credit_applied, total)."""
    charge_cap = None
    if p.plan_fee is not None and p.overage is not None and p.tax is not None:
        charge_cap = oround(p.plan_fee + p.overage + p.tax, 2)
    credit_app = min(p.credit, charge_cap if charge_cap is not None else p.credit)
    return [
        (1, "plan", p.plan_code, oround(p.plan_fee, 2), Decimal(0), Decimal(0), oround(p.plan_fee, 2)),
        (2, "usage", "usage overage", oround(p.overage, 2), Decimal(0), Decimal(0), oround(p.overage, 2)),
        (3, "tax", "regional tax", _half(p.tax), Decimal(0), Decimal(0), _half(p.tax)),
        (4, "tax", "local tax", _half(p.tax), Decimal(0), Decimal(0), _half(p.tax)),
        (5, "credit", "credit notes", Decimal(0), Decimal(0), credit_app, _neg(credit_app)),
    ]


def invoice_preview(tenant_id, period_start, period_end):
    p = compute_preview(tenant_id, period_start, period_end)
    return [
        {"line_no": n, "line_type": t, "description": d, "amount": num_out(a),
         "tax_amount": num_out(tx), "credit_applied": num_out(c), "total": num_out(tot)}
        for n, t, d, a, tx, c, tot in _preview_lines(p)
    ]


def invoice_lines(invoice_id):
    """pkg_invoicing.fn_invoice_lines: lines[] of one document, ordered by lineNo."""
    inv = db().invoices.find_one({"_id": invoice_id}, {"lines": 1})
    if not inv:
        return []
    return [
        {"line_no": ln.get("lineNo"), "line_type": ln.get("lineType"),
         "description": ln.get("description"), "amount": num_out(ln.get("amount"))}
        for ln in sorted(inv.get("lines", []), key=lambda ln: ln.get("lineNo", 0))
    ]


def issue_invoice(tenant_id, period_start, period_end):
    """pkg_invoicing.sp_issue_invoice: invoice + lines as one document write."""
    start, end = trunc(period_start), trunc(period_end)
    period_id = md5_uuid(f"{tenant_id}{ymd(start)}")
    invoice_id = md5_uuid(f"{period_id}invoice")

    rating.finalize_rating(tenant_id, start, end)
    preview = compute_preview(tenant_id, start, end)

    subtotal = tax = total = credit = Decimal(0)
    lines = []
    for line_no, line_type, descr, amount, _tax_amt, credit_app, line_total in _preview_lines(preview):
        stored_amount = line_total if line_type == "credit" else amount
        lines.append(strip_none({
            "id": md5_uuid(f"{invoice_id}{line_no}"),
            "invoiceId": invoice_id,
            "lineNo": line_no,
            "lineType": line_type,
            "description": descr,
            "amount": money(stored_amount),
        }))
        if line_type in ("plan", "usage"):
            subtotal = _nvl_add(subtotal, oround(amount, 2))
        elif line_type == "tax":
            tax = _nvl_add(tax, oround(amount, 2))
        elif line_type == "credit":
            credit = credit_app
    total = _nvl_round(subtotal, tax, credit)

    doc = strip_none({
        "_id": invoice_id, "id": invoice_id, "tenantId": tenant_id, "periodId": period_id,
        "issuedAt": end,
        "subtotal": money(oround(subtotal, 2)), "tax": money(oround(tax, 2)), "total": money(total),
        "statusCd": INV_STATUS_ISSUED, "lines": lines,
    })
    # INSERT / DUP_VAL_ON_INDEX -> UPDATE, DELETE lines, INSERT lines, UPDATE totals: one write.
    # The original keeps the original issued_at on re-issue; so do we.
    existing = db().invoices.find_one({"_id": invoice_id}, {"issuedAt": 1})
    if existing and existing.get("issuedAt") is not None:
        doc["issuedAt"] = existing["issuedAt"]
    db().invoices.replace_one({"_id": invoice_id}, doc, upsert=True)

    _burn_down_credit(tenant_id, credit)
    return invoice_id


def _nvl_add(acc, value):
    """v := v + NULL leaves the PL/SQL accumulator NULL; mirror that."""
    if acc is None or value is None:
        return None
    return acc + value


def _nvl_round(subtotal, tax, credit):
    if subtotal is None or tax is None or credit is None:
        return None
    return oround(subtotal + tax - credit, 2)


def _burn_down_credit(tenant_id, credit):
    """Oldest-first burn-down, decrementing the same running counter (quirks preserved)."""
    if credit is None or credit <= 0:
        return
    notes = db().credit_notes.find(
        {"tenantId": tenant_id, "remainingAmount": {"$gt": 0}}
    ).sort([("issuedOn", ASCENDING), ("_id", ASCENDING)])
    for note in notes:
        if credit <= 0:
            break
        remaining = dec(note["remainingAmount"])
        db().credit_notes.update_one(
            {"_id": note["_id"]},
            {"$set": {"remainingAmount": money(max(remaining - credit, Decimal(0)))}},
        )
        credit = max(credit - remaining, Decimal(0))


def list_invoices(tenant_id):
    """facade GET /invoices: invoices JOIN rating_periods LEFT JOIN codes(INV_STATUS)."""
    out = []
    for inv in db().invoices.find({"tenantId": tenant_id}).sort([("issuedAt", DESCENDING), ("_id", DESCENDING)]):
        period = db().rating_periods.find_one({"_id": inv.get("periodId")}) if inv.get("periodId") else None
        if period is None:  # inner JOIN
            continue
        status = (shared_reference.code_desc("INV_STATUS", inv.get("statusCd"))
                  if inv.get("statusCd") is not None else None)
        out.append({
            "invoice_id": inv["_id"],
            "period_start": period.get("periodStart"),
            "period_end": period.get("periodEnd"),
            "subtotal": num_out(inv.get("subtotal")),
            "tax": num_out(inv.get("tax")),
            "total": num_out(inv.get("total")),
            "status": status,
        })
    return out
