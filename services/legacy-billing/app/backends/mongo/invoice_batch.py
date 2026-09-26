"""Unit invoice_batch: invoice_headers + invoice_lines (wave 1, batch w1-b02, mapping v1.1.0).

Ports app/reports.py (legacy RPT-114 month-end rollup, Oracle SQL) to aggregation pipelines
over mmp_rt_billing.invoice_headers and the referenced collection invoice_lines
(halt fix A: lines are NOT embedded; invoice_lines._id = LINE_ID, invoice_lines.invoiceId
references invoice_headers._id).
- STATUS_SQL -> month_end_by_status(batch_no):
      header count + SUM(total_amt) per status, status label = codes(INV_STATUS).codeDesc or
      'UNKNOWN(<statusCd>)' (the NVL over the outer join), ordered by label.
- LINE_SQL   -> month_end_by_status_line_type(batch_no):
      $lookup invoice_lines on invoiceId + $unwind (the inner join header x line: a header
      with no lines contributes no row, exactly like Oracle), grouped by status label x
      DECODE(line_type_cd), with COUNT(*), SUM(amount), SUM(tax_amt),
      COUNT(DISTINCT invoice_id), ordered by 1, 2.
Orphaned INVOICE_LINE rows (orphan:true, no header) fall out of the join in Oracle and
never match a $lookup here, so the numbers match without filtering on the flag.

Money renders like TO_CHAR(SUM(x), 'FM999999999999990.00'): plain decimal string, 2 places
(SUM of all-NULL is NULL -> Oracle emits NULL -> None here).
Reads codes (wave-0) read-only. Writes nothing.
"""
from decimal import Decimal

from . import db
from ._util import dec

INV_STATUS = "INV_STATUS"
LINE_TYPES = {1: "CHARGE", 2: "CREDIT", 3: "ADJUSTMENT", 9: "MISC"}
INDEX_PLAN = {  # mapping v1.1.0
    "invoice_headers": ["{batchNo:1, statusCd:1}", "{custId:1}", "{tenantId:1}"],
    "invoice_lines": ["{invoiceId:1, lineNo:1}", "{orphan:1}"],
}


def fm_money(value):
    """TO_CHAR(n, 'FM999999999999990.00'): fixed 2 decimals, no padding; NULL -> None."""
    if value is None:
        return None
    return str(dec(value).quantize(Decimal("0.01")))


def _status_label_stages():
    """codes(INV_STATUS) outer join + NVL(code_desc, 'UNKNOWN(' || status_cd || ')')."""
    return [
        {"$lookup": {
            "from": "codes",
            "let": {"cd": "$statusCd"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$_id.codeType", INV_STATUS]},
                    {"$eq": ["$_id.codeVal", "$$cd"]},
                ]}}},
                {"$project": {"_id": 0, "codeDesc": 1}},
            ],
            "as": "_st",
        }},
        {"$addFields": {"statusDesc": {"$ifNull": [
            {"$first": "$_st.codeDesc"},
            {"$concat": ["UNKNOWN(", {"$toString": {"$ifNull": ["$statusCd", ""]}}, ")"]},
        ]}}},
    ]


def _lines_join_stages():
    """h.invoice_id = l.invoice_id (inner join): $lookup on invoiceId, $unwind drops headers
    with no lines. Uses the {invoiceId:1, lineNo:1} index on invoice_lines."""
    return [
        {"$lookup": {
            "from": "invoice_lines",
            "localField": "_id",
            "foreignField": "invoiceId",
            "as": "lines",
        }},
        {"$unwind": "$lines"},
    ]


def _line_type_expr():
    """DECODE(l.line_type_cd, 1,'CHARGE', 2,'CREDIT', 3,'ADJUSTMENT', 9,'MISC', 'UNKNOWN(cd)')."""
    return {"$switch": {
        "branches": [{"case": {"$eq": ["$lines.lineTypeCd", cd]}, "then": label}
                     for cd, label in LINE_TYPES.items()],
        "default": {"$concat": ["UNKNOWN(", {"$toString": {"$ifNull": ["$lines.lineTypeCd", ""]}}, ")"]},
    }}


def month_end_by_status(batch_no):
    """STATUS_SQL: [(status_desc, invoice_count, header_total_amt), ...] ordered by status."""
    pipeline = [
        {"$match": {"batchNo": int(batch_no)}},
        *_status_label_stages(),
        {"$group": {"_id": "$statusDesc",
                    "invoice_count": {"$sum": 1},
                    "header_total_amt": {"$sum": "$totalAmt"},
                    "has_amt": {"$max": {"$cond": [{"$ne": ["$totalAmt", None]}, 1, 0]}}}},
        {"$sort": {"_id": 1}},
    ]
    return [(r["_id"], r["invoice_count"], fm_money(r["header_total_amt"]) if r["has_amt"] else None)
            for r in db().invoice_headers.aggregate(pipeline)]  # default (binary) sort = Oracle NLS_SORT=BINARY


def month_end_by_status_line_type(batch_no):
    """LINE_SQL: [(status_desc, line_type, line_count, line_amount, line_tax, invoices_touched), ...]."""
    pipeline = [
        {"$match": {"batchNo": int(batch_no)}},
        *_status_label_stages(),
        *_lines_join_stages(),
        {"$group": {"_id": {"status": "$statusDesc", "lineType": _line_type_expr()},
                    "line_count": {"$sum": 1},
                    "line_amount": {"$sum": "$lines.amount"},
                    "has_amount": {"$max": {"$cond": [{"$ne": ["$lines.amount", None]}, 1, 0]}},
                    "line_tax": {"$sum": "$lines.taxAmt"},
                    "has_tax": {"$max": {"$cond": [{"$ne": ["$lines.taxAmt", None]}, 1, 0]}},
                    "invoices": {"$addToSet": "$_id"}}},
        {"$project": {"line_count": 1, "line_amount": 1, "has_amount": 1, "line_tax": 1, "has_tax": 1,
                      "invoices_touched": {"$size": "$invoices"}}},
        {"$sort": {"_id.status": 1, "_id.lineType": 1}},
    ]
    return [(r["_id"]["status"], r["_id"]["lineType"], r["line_count"],
             fm_money(r["line_amount"]) if r["has_amount"] else None,
             fm_money(r["line_tax"]) if r["has_tax"] else None,
             r["invoices_touched"])
            for r in db().invoice_headers.aggregate(pipeline)]


def invoice_header(invoice_id):
    """Point read: one header (INVOICE_HEADER by INVOICE_ID)."""
    return db().invoice_headers.find_one({"_id": invoice_id})


def invoice_lines(invoice_id):
    """INVOICE_LINE rows of one invoice, ordered by LINE_NO (replaces the header x line join)."""
    return list(db().invoice_lines.find({"invoiceId": invoice_id}).sort("lineNo", 1))


def orphan_lines(limit=100):
    """Planted INVOICE_LINE rows with no INVOICE_HEADER (derived flag), kept for finance review."""
    return list(db().invoice_lines.find({"orphan": True}).sort("_id", 1).limit(limit))
