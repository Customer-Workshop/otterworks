"""Month-end finance reporting served straight from the Oracle billing estate.

The report is the legacy RPT-114 rollup (see
db/oracle/ops/OPERATIONS_HANDBOOK.doc.txt and the CODES lookup conventions):
invoice counts and header totals by status, plus a line rollup by status and
line type. Orphaned INVOICE_LINE rows fall out of the join, exactly as finance
always ran it. Rows are namespace-scoped through the deterministic
conversion batch number.
"""

import hashlib
import logging
import csv
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, jsonify, request

from oracle_conn import oracle_connect as connect_oracle

reports = Blueprint("reports", __name__)
logger = logging.getLogger(__name__)

ESTATE_UNAVAILABLE = {
    "error": "legacy estate unavailable",
    "detail": "the Oracle billing estate is not reachable; try again later",
}

SOURCE = {
    "engine": "oracle",
    "system": "OW_BILLING legacy estate (Oracle FREEPDB1)",
    "detail": "INVOICE_HEADER / INVOICE_LINE via CODES lookup (RPT-114)",
}

FINANCE_SOURCE = {
    "system": "CUSTBILL month-end batch",
    "detail": "ksh/Perl chain over Oracle CUSTBILL extract",
}

STATUS_SQL = """
SELECT NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')') AS status_desc,
       COUNT(*)                                   AS invoice_count,
       TO_CHAR(SUM(h.total_amt), 'FM999999999999990.00') AS header_total_amt
  FROM invoice_header h,
       codes st
 WHERE h.batch_no = :batch_no
   AND st.code_type (+) = 'INV_STATUS'
   AND st.code_val  (+) = h.status_cd
 GROUP BY NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')')
 ORDER BY 1
"""

LINE_SQL = """
SELECT NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')') AS status_desc,
       DECODE(l.line_type_cd, 1, 'CHARGE',
                              2, 'CREDIT',
                              3, 'ADJUSTMENT',
                              9, 'MISC',
                              'UNKNOWN(' || TO_CHAR(l.line_type_cd) || ')')
                                                  AS line_type,
       COUNT(*)                                   AS line_count,
       TO_CHAR(SUM(l.amount),  'FM999999999999990.00') AS line_amount,
       TO_CHAR(SUM(l.tax_amt), 'FM999999999999990.00') AS line_tax,
       COUNT(DISTINCT h.invoice_id)               AS invoices_touched
  FROM invoice_header h,
       invoice_line   l,
       codes          st
 WHERE h.batch_no = :batch_no
   AND h.invoice_id = l.invoice_id
   AND st.code_type (+) = 'INV_STATUS'
   AND st.code_val  (+) = h.status_cd
 GROUP BY NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')'),
          DECODE(l.line_type_cd, 1, 'CHARGE',
                                 2, 'CREDIT',
                                 3, 'ADJUSTMENT',
                                 9, 'MISC',
                                 'UNKNOWN(' || TO_CHAR(l.line_type_cd) || ')')
 ORDER BY 1, 2
"""

BALANCES_SQL = """
SELECT COUNT(*)                                          AS customer_count,
       TO_CHAR(SUM(cur_bal_amt), 'FM999999999999990.00') AS current_balance_total,
       TO_CHAR(SUM(past_due_amt), 'FM999999999999990.00') AS past_due_total
  FROM customer_master
 WHERE conversion_batch_no = :batch_no
"""


def ns_batch_no(ns):
    """Deterministic conversion batch number for a namespace.

    Mirrors testdata/legacy/legacy_common.ns_seed + oracle_billing_seed:
    sha256(ns)[:8] as int, folded into the 8-digit NUMBER(8) batch range.
    """
    seed = int(hashlib.sha256(ns.encode()).hexdigest()[:8], 16)
    return seed % 90_000_000 + 1_000_000


def shape_status_rows(rows):
    return [
        {"status": status, "invoice_count": count, "header_total_amt": total}
        for status, count, total in rows
    ]


def shape_line_rows(rows):
    return [
        {
            "status": status,
            "line_type": line_type,
            "line_count": line_count,
            "line_amount": line_amount,
            "line_tax": line_tax,
            "invoices_touched": invoices_touched,
        }
        for status, line_type, line_count, line_amount, line_tax, invoices_touched in rows
    ]


def shape_balances(row):
    customer_count, current_total, past_due_total = row
    return {
        "customer_count": customer_count,
        "current_balance_total": current_total,
        "past_due_total": past_due_total,
    }


class FinanceReportTooLarge(Exception):
    pass


def oracle_query(sql, params):
    with connect_oracle() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def report_meta(ns):
    return {
        "namespace": ns,
        "batch_no": ns_batch_no(ns),
        "source": SOURCE,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _admin_report_allowed():
    return "ADMIN" in {
        role.strip().upper()
        for role in request.headers.get("X-User-Roles", "").split(",")
        if role.strip()
    }


@reports.get("/api/reports/month-end")
def month_end():
    ns = request.args.get("ns", "demo")
    batch_no = ns_batch_no(ns)
    try:
        status_rows = oracle_query(STATUS_SQL, {"batch_no": batch_no})
        line_rows = oracle_query(LINE_SQL, {"batch_no": batch_no})
    except Exception:  # estate offline: fail closed, never fabricate numbers
        logger.exception("month-end report failed for ns=%s", ns)
        return jsonify(ESTATE_UNAVAILABLE), 503
    body = report_meta(ns)
    body["report"] = "month-end-finance"
    body["by_status"] = shape_status_rows(status_rows)
    body["by_status_line_type"] = shape_line_rows(line_rows)
    return jsonify(body)


@reports.get("/api/v1/billing/admin/reports/month-end")
def admin_month_end():
    if not _admin_report_allowed():
        return jsonify(error="forbidden"), 403
    return month_end()


@reports.get("/api/reports/reconciliation")
def reconciliation():
    ns = request.args.get("ns", "demo")
    batch_no = ns_batch_no(ns)
    try:
        balance_rows = oracle_query(BALANCES_SQL, {"batch_no": batch_no})
    except Exception:
        logger.exception("reconciliation report failed for ns=%s", ns)
        return jsonify(ESTATE_UNAVAILABLE), 503
    body = report_meta(ns)
    body["balances"] = shape_balances(balance_rows[0])
    # The legacy estate IS the source of truth: there is nothing to reconcile
    # against, so it reports baseline with no checks. Post-migration backends
    # return status pass|fail with per-check results instead.
    body["status"] = "baseline"
    body["checks"] = []
    return jsonify(body)


@reports.get("/api/v1/billing/admin/reports/reconciliation")
def admin_reconciliation():
    if not _admin_report_allowed():
        return jsonify(error="forbidden"), 403
    return reconciliation()


def finance_report_dir():
    configured = os.getenv("FINANCE_REPORT_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "etl/legacy-extra/reports"


def finance_report_path(ns):
    if not ns or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in ns):
        return None
    directory = finance_report_dir() / ns
    reports = sorted(
        directory.glob("finance_billing_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def parse_finance_report(path):
    max_bytes = int(os.getenv("FINANCE_REPORT_MAX_BYTES", str(50 * 1024 * 1024)))
    if path.stat().st_size > max_bytes:
        raise FinanceReportTooLarge
    with path.open(newline="", encoding="utf-8") as stream:
        rows = []
        total_count = 0
        total_amount = Decimal("0.00")
        for row in csv.DictReader(stream):
            record_count = int(row["RecordCount"])
            total_count += record_count
            total_amount += Decimal(row["TotalAmount"])
            rows.append(
                {
                    "currency": row["Currency"],
                    "record_type": row["RecordType"],
                    "record_count": record_count,
                    "total_amount": row["TotalAmount"],
                }
            )
    return rows, {
        "record_count": total_count,
        "total_amount": f"{total_amount:.2f}",
    }


@reports.get("/api/reports/finance")
def finance():
    ns = request.args.get("ns", "demo")
    path = finance_report_path(ns)
    if path is None:
        return jsonify({
            "error": "no finance report for namespace",
            "detail": "run make tp-month-end NS=" + ns,
        }), 404
    try:
        rows, totals = parse_finance_report(path)
    except FinanceReportTooLarge:
        return jsonify(error="finance report too large"), 413
    generated_at = datetime.fromtimestamp(
        path.stat().st_mtime, timezone.utc,
    ).isoformat()
    return jsonify({
        "ns": ns,
        "source": {
            **FINANCE_SOURCE,
            "generated_at": generated_at,
            "file": path.name,
        },
        "rows": rows,
        "totals": totals,
    })


@reports.get("/api/v1/billing/admin/reports/finance")
def admin_finance():
    if not _admin_report_allowed():
        return jsonify(error="forbidden"), 403
    return finance()
