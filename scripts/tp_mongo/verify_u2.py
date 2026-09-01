#!/usr/bin/env python3
"""Produce supplemental U2 evidence for quarantine and report parity."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import Decimal128

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
QUARANTINE_DB = "ow_tp_mongodb_032752_quarantine"
FEED_COLLECTION = "invoice_feed"
ORPHAN_COLLECTION = "invoice_feed_orphan_lines"
REPO_ROOT = Path(__file__).resolve().parents[1].parent

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

TOTAL_LINE_COUNT_SQL = "SELECT COUNT(*) FROM INVOICE_LINE"
MATCHED_LINE_COUNT_SQL = (
    "SELECT COUNT(*) FROM INVOICE_LINE WHERE EXISTS "
    "(SELECT 1 FROM INVOICE_HEADER H WHERE H.INVOICE_ID = INVOICE_LINE.INVOICE_ID)"
)
ORPHAN_LINE_IDS_SQL = (
    "SELECT LINE_ID FROM INVOICE_LINE WHERE NOT EXISTS "
    "(SELECT 1 FROM INVOICE_HEADER H WHERE H.INVOICE_ID = INVOICE_LINE.INVOICE_ID) "
    "ORDER BY LINE_ID"
)


def _args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / ".migration/recon/U2/supplemental.json"),
    )
    parser.add_argument("--dsn-secret", default="OW_BILLING_FIXTURE_DSN")
    parser.add_argument("--uri-secret", default="MONGODB_ATLAS_URI")
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _oracle_connection(secret_name: str):
    import oracledb

    value = _secret_value(secret_name, "Oracle DSN secret")
    try:
        user, password, dsn = value.split("/", 2)
    except ValueError as exc:
        raise RuntimeError(
            f"Oracle DSN secret '{secret_name}' must contain user/password/dsn"
        ) from exc
    if not user or not password or not dsn:
        raise RuntimeError(
            f"Oracle DSN secret '{secret_name}' must contain non-empty user/password/dsn"
        )
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _oracle_query(connection, sql: str, params: dict | None = None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or {})
        return cursor.fetchall()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _first_differences(left: list, right: list, limit: int = 5) -> list[dict]:
    differences = []
    for index in range(max(len(left), len(right))):
        actual_left = left[index] if index < len(left) else None
        actual_right = right[index] if index < len(right) else None
        if actual_left != actual_right:
            differences.append(
                {"index": index, "legacy": actual_left, "mongo": actual_right}
            )
            if len(differences) == limit:
                break
    return differences


def _aggregate_embedded_lines(feed) -> int:
    result = next(
        feed.aggregate(
            [
                {
                    "$group": {
                        "_id": None,
                        "embedded_lines": {"$sum": {"$size": "$lines"}},
                    }
                }
            ]
        ),
        {"embedded_lines": 0},
    )
    return int(result["embedded_lines"])


def main() -> int:
    args = _args()
    sys.path.insert(0, str(REPO_ROOT / "services/legacy-billing/app"))
    import reports

    from pymongo import MongoClient

    batch_no = reports.ns_batch_no("demo")
    oracle = _oracle_connection(args.dsn_secret)
    client = MongoClient(_secret_value(args.uri_secret, "Mongo URI secret"))
    try:
        total_line_rows = int(
            _oracle_query(oracle, TOTAL_LINE_COUNT_SQL)[0][0]
        )
        matched_line_rows = int(
            _oracle_query(oracle, MATCHED_LINE_COUNT_SQL)[0][0]
        )
        orphan_line_rows = total_line_rows - matched_line_rows
        orphan_ids = {
            str(row[0]) for row in _oracle_query(oracle, ORPHAN_LINE_IDS_SQL)
        }
        legacy_status_rows = reports.shape_status_rows(
            _oracle_query(oracle, STATUS_SQL, {"batch_no": batch_no})
        )
        legacy_line_rows = reports.shape_line_rows(
            _oracle_query(oracle, LINE_SQL, {"batch_no": batch_no})
        )

        feed = client[TARGET_DB][FEED_COLLECTION]
        quarantine = client[QUARANTINE_DB][ORPHAN_COLLECTION]
        embedded_lines = _aggregate_embedded_lines(feed)
        quarantined_count = quarantine.count_documents({})
        target_orphan_ids = {str(doc["_id"]) for doc in quarantine.find({}, {"_id": 1})}
        invalid_quarantine_docs = list(
            quarantine.find(
                {
                    "$or": [
                        {"reason_class": {"$ne": "orphan_fk"}},
                        {"unit": {"$ne": "U2"}},
                        {"ns": {"$ne": NS_VALUE}},
                    ]
                },
                {"_id": 1, "reason_class": 1, "unit": 1, "ns": 1},
            )
        )

        mongo_status_rows = reports.shape_status_rows(
            reports.status_report_rows(batch_no)
        )
        mongo_line_rows = reports.shape_line_rows(reports.line_report_rows(batch_no))
        status_differences = _first_differences(
            legacy_status_rows, mongo_status_rows
        )
        line_differences = _first_differences(legacy_line_rows, mongo_line_rows)

        cardinality = {
            "oracle_total": total_line_rows,
            "oracle_matched": matched_line_rows,
            "oracle_orphan": orphan_line_rows,
            "target_embedded": embedded_lines,
            "target_quarantined": quarantined_count,
            "embedded_plus_quarantined": embedded_lines + quarantined_count,
            "total_pass": total_line_rows == 150000,
            "matched_pass": matched_line_rows == 149963,
            "orphan_pass": orphan_line_rows == 37,
            "target_embedded_pass": embedded_lines == matched_line_rows,
            "target_quarantined_pass": quarantined_count == orphan_line_rows,
            "balanced": embedded_lines + quarantined_count == total_line_rows,
        }
        orphan_identity = {
            "oracle_count": len(orphan_ids),
            "target_count": len(target_orphan_ids),
            "missing_ids": sorted(orphan_ids - target_orphan_ids),
            "unexpected_ids": sorted(target_orphan_ids - orphan_ids),
            "invalid_quarantine_docs": [
                {key: (str(value) if isinstance(value, Decimal128) else value)
                 for key, value in doc.items()}
                for doc in invalid_quarantine_docs
            ],
        }
        orphan_identity["pass"] = not (
            orphan_identity["missing_ids"]
            or orphan_identity["unexpected_ids"]
            or orphan_identity["invalid_quarantine_docs"]
        ) and len(orphan_ids) == 37
        report_parity = {
            "batch_no": batch_no,
            "status": {
                "legacy_row_count": len(legacy_status_rows),
                "mongo_row_count": len(mongo_status_rows),
                "first_5_differences": status_differences,
                "pass": not status_differences
                and len(legacy_status_rows) == len(mongo_status_rows),
            },
            "line": {
                "legacy_row_count": len(legacy_line_rows),
                "mongo_row_count": len(mongo_line_rows),
                "first_5_differences": line_differences,
                "pass": not line_differences
                and len(legacy_line_rows) == len(mongo_line_rows),
            },
        }
        report_parity["pass"] = (
            report_parity["status"]["pass"] and report_parity["line"]["pass"]
        )
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "unit": "U2",
            "namespace": NS_VALUE,
            "cardinality": cardinality,
            "orphan_identity": orphan_identity,
            "report_parity": report_parity,
            "pass": (
                all(
                    value
                    for key, value in cardinality.items()
                    if key.endswith("_pass") or key == "balanced"
                )
                and orphan_identity["pass"]
                and report_parity["pass"]
            ),
        }
        _write(Path(args.out), payload)
        print(
            f"U2 supplemental verification: pass={payload['pass']} "
            f"embedded={embedded_lines} quarantined={quarantined_count} "
            f"status_rows={len(mongo_status_rows)} line_rows={len(mongo_line_rows)}"
        )
        return 0 if payload["pass"] else 1
    finally:
        client.close()
        oracle.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
