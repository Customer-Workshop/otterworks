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
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, jsonify, request

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

MONGO_SOURCE = {
    "engine": "mongodb",
    "system": "ow_tp_mongodb_032752 (MongoDB Atlas)",
    "detail": "customers aggregation pipeline (RPT-114 balances)",
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


def balances_pipeline(batch_no):
    return [
        {"$match": {"conversion_batch_no": batch_no}},
        {"$group": {"_id": None,
                    "customer_count": {"$sum": 1},
                    "current_balance_total": {"$sum": "$cur_bal_amt"},
                    "past_due_total": {"$sum": "$past_due_amt"}}},
    ]


def fm_amount(value):
    """Render a NUMBER(14,2) aggregate the way TO_CHAR(x, 'FM999999999999990.00') does."""
    if value is None:
        return None
    quantized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized:f}"


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


def oracle_connect():
    import oracledb

    return oracledb.connect(
        user=os.getenv("ORACLE_USER", "ow_billing"),
        password=os.getenv("ORACLE_PASSWORD", "ow_billing"),
        host=os.getenv("ORACLE_HOST", "localhost"),
        port=int(os.getenv("ORACLE_PORT", "52521")),
        service_name=os.getenv("ORACLE_SERVICE", "FREEPDB1"),
    )


def oracle_query(sql, params):
    with oracle_connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def mongo_connect():
    import pymongo

    return pymongo.MongoClient(os.environ["OW_BILLING_MONGO_URI"])


def _customers_collection(client):
    return client[os.getenv("OW_BILLING_MONGO_DB", "ow_tp_mongodb_032752")]["customers"]


def mongo_balances(batch_no):
    client = mongo_connect()
    try:
        rows = list(
            _customers_collection(client).aggregate(balances_pipeline(batch_no))
        )
    finally:
        client.close()
    if not rows:
        # Mirrors Oracle's COUNT(*)=0 with SUM(...) NULL over an empty match.
        return [(0, None, None)]
    row = rows[0]
    return [
        (
            row["customer_count"],
            fm_amount(row["current_balance_total"]),
            fm_amount(row["past_due_total"]),
        )
    ]


def balances_backend():
    backend = os.getenv("BILLING_BALANCES_BACKEND")
    if backend is not None:
        backend = backend.lower()
        if backend not in ("oracle", "mongodb"):
            raise ValueError(f"unknown balances backend: {backend}")
        return backend
    return "mongodb" if os.getenv("OW_BILLING_MONGO_URI") else "oracle"


def report_meta(ns, source=SOURCE):
    return {
        "namespace": ns,
        "batch_no": ns_batch_no(ns),
        "source": source,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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


@reports.get("/api/reports/reconciliation")
def reconciliation():
    ns = request.args.get("ns", "demo")
    batch_no = ns_batch_no(ns)
    backend = balances_backend()
    try:
        if backend == "mongodb":
            balance_rows = mongo_balances(batch_no)
        else:
            balance_rows = oracle_query(BALANCES_SQL, {"batch_no": batch_no})
    except Exception:
        logger.exception("reconciliation report failed for ns=%s", ns)
        return jsonify(ESTATE_UNAVAILABLE), 503
    body = report_meta(ns, MONGO_SOURCE if backend == "mongodb" else SOURCE)
    body["balances"] = shape_balances(balance_rows[0])
    # The legacy estate IS the source of truth: there is nothing to reconcile
    # against, so it reports baseline with no checks. Post-migration backends
    # return status pass|fail with per-check results instead.
    body["status"] = "baseline"
    body["checks"] = []
    return jsonify(body)
