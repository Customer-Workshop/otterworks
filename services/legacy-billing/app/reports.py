"""Month-end finance reporting served from the migrated invoice collection.

The report is the legacy RPT-114 rollup (see
db/oracle/ops/OPERATIONS_HANDBOOK.doc.txt and the CODES lookup conventions):
invoice counts and header totals by status, plus a line rollup by status and
line type. The month-end rollup is served from the migrated collection while
reconciliation still reads Oracle. Orphaned INVOICE_LINE rows are quarantined
and therefore are not embedded in the migrated collection. Rows are
namespace-scoped through the deterministic conversion batch number.
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
    "system": "MongoDB Atlas migration target (ow_tp_mongodb_032752)",
    "detail": "invoice_feed roots with embedded lines[] via the codes lookup (RPT-114 port)",
}

MONGO_BALANCES_SOURCE = {
    "engine": "mongodb",
    "system": "ow_tp_mongodb_032752 (MongoDB Atlas)",
    "detail": "customers aggregation pipeline (RPT-114 balances)",
}

_mongo_client = None

ORACLE_AMOUNT_OVERFLOW_MARKER = "#" * 19
ORACLE_AMOUNT_OVERFLOW_LIMIT = Decimal("1000000000000000")

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
                    "current_balance_count": {
                        "$sum": {"$cond": [{"$isNumber": "$cur_bal_amt"}, 1, 0]}},
                    "past_due_total": {"$sum": "$past_due_amt"},
                    "past_due_count": {
                        "$sum": {"$cond": [{"$isNumber": "$past_due_amt"}, 1, 0]}}}},
    ]


def fm_amount(value):
    """Render a NUMBER(14,2) aggregate the way TO_CHAR(x, 'FM999999999999990.00') does."""
    if value is None:
        return None
    quantized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(quantized) >= ORACLE_AMOUNT_OVERFLOW_LIMIT:
        return ORACLE_AMOUNT_OVERFLOW_MARKER
    return f"{quantized:f}"


def _oracle_sum(total, present):
    return fm_amount(total) if present else None


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


def status_pipeline(batch_no):
    return [
        {"$match": {"batch_no": batch_no}},
        {
            "$group": {
                "_id": "$status_cd",
                "invoice_count": {"$sum": 1},
                "header_total_amt": {"$sum": "$total_amt"},
            }
        },
        {
            "$set": {
                "code_key": {
                    "$concat": [
                        "INV_STATUS#",
                        {"$toString": {"$ifNull": ["$_id", ""]}},
                    ]
                }
            }
        },
        {
            "$lookup": {
                "from": "codes",
                "localField": "code_key",
                "foreignField": "_id",
                "as": "code",
            }
        },
        {
            "$set": {
                "status_desc": {
                    "$ifNull": [
                        {"$first": "$code.code_desc"},
                        {
                            "$concat": [
                                "UNKNOWN(",
                                {"$toString": {"$ifNull": ["$_id", ""]}},
                                ")",
                            ]
                        },
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$status_desc",
                "invoice_count": {"$sum": "$invoice_count"},
                "header_total_amt": {"$sum": "$header_total_amt"},
            }
        },
        {"$sort": {"_id": 1}},
    ]


def line_pipeline(batch_no):
    return [
        {"$match": {"batch_no": batch_no}},
        {"$unwind": "$lines"},
        {
            "$group": {
                "_id": {
                    "status_cd": "$status_cd",
                    "line_type_cd": "$lines.line_type_cd",
                    "invoice_id": "$_id",
                },
                "line_count": {"$sum": 1},
                "line_amount": {"$sum": "$lines.amount"},
                "line_tax": {"$sum": "$lines.tax_amt"},
            }
        },
        {
            "$group": {
                "_id": {
                    "status_cd": "$_id.status_cd",
                    "line_type_cd": "$_id.line_type_cd",
                },
                "line_count": {"$sum": "$line_count"},
                "line_amount": {"$sum": "$line_amount"},
                "line_tax": {"$sum": "$line_tax"},
                "invoices_touched": {"$sum": 1},
            }
        },
        {
            "$set": {
                "code_key": {
                    "$concat": [
                        "INV_STATUS#",
                        {"$toString": {"$ifNull": ["$_id.status_cd", ""]}},
                    ]
                }
            }
        },
        {
            "$lookup": {
                "from": "codes",
                "localField": "code_key",
                "foreignField": "_id",
                "as": "code",
            }
        },
        {
            "$set": {
                "status_desc": {
                    "$ifNull": [
                        {"$first": "$code.code_desc"},
                        {
                            "$concat": [
                                "UNKNOWN(",
                                {
                                    "$toString": {
                                        "$ifNull": ["$_id.status_cd", ""]
                                    }
                                },
                                ")",
                            ]
                        },
                    ]
                },
                "line_type": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {"$eq": ["$_id.line_type_cd", 1]},
                                "then": "CHARGE",
                            },
                            {
                                "case": {"$eq": ["$_id.line_type_cd", 2]},
                                "then": "CREDIT",
                            },
                            {
                                "case": {"$eq": ["$_id.line_type_cd", 3]},
                                "then": "ADJUSTMENT",
                            },
                            {
                                "case": {"$eq": ["$_id.line_type_cd", 9]},
                                "then": "MISC",
                            },
                        ],
                        "default": {
                            "$concat": [
                                "UNKNOWN(",
                                {
                                    "$toString": {
                                        "$ifNull": ["$_id.line_type_cd", ""]
                                    }
                                },
                                ")",
                            ]
                        },
                    }
                },
            }
        },
        {
            "$group": {
                "_id": {
                    "status_desc": "$status_desc",
                    "line_type": "$line_type",
                },
                "line_count": {"$sum": "$line_count"},
                "line_amount": {"$sum": "$line_amount"},
                "line_tax": {"$sum": "$line_tax"},
                "invoices_touched": {"$sum": "$invoices_touched"},
            }
        },
        {"$sort": {"_id.status_desc": 1, "_id.line_type": 1}},
    ]


def mongo_client():
    global _mongo_client

    if _mongo_client is not None:
        return _mongo_client

    from pymongo import MongoClient

    _mongo_client = MongoClient(os.environ["MONGODB_ATLAS_URI"])
    return _mongo_client


def mongo_db():
    return mongo_client()[os.getenv("MONGO_MIGRATION_DB", "ow_tp_mongodb_032752")]


def mongo_aggregate(collection, pipeline):
    return list(mongo_db()[collection].aggregate(pipeline))


def amount_str(value):
    if hasattr(value, "to_decimal"):
        value = value.to_decimal()
    return f"{Decimal(value):.2f}"


def status_report_rows(batch_no):
    return [
        (
            doc["_id"],
            int(doc["invoice_count"]),
            amount_str(doc["header_total_amt"]),
        )
        for doc in mongo_aggregate("invoice_feed", status_pipeline(batch_no))
    ]


def line_report_rows(batch_no):
    return [
        (
            doc["_id"]["status_desc"],
            doc["_id"]["line_type"],
            int(doc["line_count"]),
            amount_str(doc["line_amount"]),
            amount_str(doc["line_tax"]),
            int(doc["invoices_touched"]),
        )
        for doc in mongo_aggregate("invoice_feed", line_pipeline(batch_no))
    ]


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
            _oracle_sum(row["current_balance_total"], row["current_balance_count"]),
            _oracle_sum(row["past_due_total"], row["past_due_count"]),
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
        status_rows = status_report_rows(batch_no)
        line_rows = line_report_rows(batch_no)
    except Exception:  # estate offline: fail closed, never fabricate numbers
        logger.exception("month-end report failed for ns=%s", ns)
        return jsonify(ESTATE_UNAVAILABLE), 503
    body = report_meta(ns, source=MONGO_SOURCE)
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
    body = report_meta(
        ns, MONGO_BALANCES_SOURCE if backend == "mongodb" else SOURCE
    )
    body["balances"] = shape_balances(balance_rows[0])
    # The legacy estate IS the source of truth: there is nothing to reconcile
    # against, so it reports baseline with no checks. Post-migration backends
    # return status pass|fail with per-check results instead.
    body["status"] = "baseline"
    body["checks"] = []
    return jsonify(body)
