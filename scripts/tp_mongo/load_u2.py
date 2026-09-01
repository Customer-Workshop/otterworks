#!/usr/bin/env python3
"""Load the U2 invoice feed from the read-only Oracle billing fixture into MongoDB."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

from bson import Decimal128

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
QUARANTINE_DB = "ow_tp_mongodb_032752_quarantine"
FEED_COLLECTION = "invoice_feed"
ORPHAN_COLLECTION = "invoice_feed_orphan_lines"
REPO_ROOT = Path(__file__).resolve().parents[1].parent

HEADERS_SQL = (
    "SELECT INVOICE_ID, INVOICE_NO, CUST_ID, TENANT_ID, INVOICE_DT, DUE_DT, "
    "STATUS_CD, TOTAL_AMT, BATCH_NO FROM INVOICE_HEADER ORDER BY INVOICE_ID"
)
MATCHED_LINES_SQL = (
    "SELECT LINE_ID, INVOICE_ID, INVOICE_NO, CUST_ID, CUST_NO, CUST_NAME, "
    "TENANT_ID, LINE_NO, LINE_TYPE_CD, ITEM_DESC, QTY, UNIT_PRICE, AMOUNT, "
    "TAX_AMT, INVOICE_DT, SERVICE_PERIOD, POSTED_YN, GL_ACCT_CSV, BATCH_NO, "
    "SRC_SYSTEM FROM INVOICE_LINE WHERE EXISTS (SELECT 1 FROM INVOICE_HEADER H "
    "WHERE H.INVOICE_ID = INVOICE_LINE.INVOICE_ID) ORDER BY INVOICE_ID, LINE_ID"
)
ORPHAN_LINES_SQL = (
    "SELECT LINE_ID, INVOICE_ID, INVOICE_NO, CUST_ID, CUST_NO, CUST_NAME, "
    "TENANT_ID, LINE_NO, LINE_TYPE_CD, ITEM_DESC, QTY, UNIT_PRICE, AMOUNT, "
    "TAX_AMT, INVOICE_DT, SERVICE_PERIOD, POSTED_YN, GL_ACCT_CSV, BATCH_NO, "
    "SRC_SYSTEM FROM INVOICE_LINE WHERE NOT EXISTS (SELECT 1 FROM INVOICE_HEADER H "
    "WHERE H.INVOICE_ID = INVOICE_LINE.INVOICE_ID) ORDER BY LINE_ID"
)
LINE_COUNT_SQL = "SELECT COUNT(*) FROM INVOICE_LINE"


def vc(v):
    """VARCHAR2 to string with empty strings represented as null."""
    return None if v is None or v == "" else str(v)


def ch(v):
    """CHAR to rstripped string with empty strings represented as null."""
    if v is None:
        return None
    value = str(v).rstrip(" ")
    return None if value == "" else value


def dec(v, scale):
    """NUMBER to half-even rounded BSON Decimal128."""
    return Decimal128(
        Decimal(str(v)).quantize(
            Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN
        )
    )


def _args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn-secret",
        default="OW_BILLING_FIXTURE_DSN",
        help="environment variable name containing user/password/dsn",
    )
    parser.add_argument(
        "--uri-secret",
        default="MONGODB_ATLAS_URI",
        help="environment variable name containing the Mongo URI",
    )
    parser.add_argument("--target-db", default=TARGET_DB)
    parser.add_argument("--quarantine-db", default=QUARANTINE_DB)
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U2/load_report.json"),
    )
    parser.add_argument("--batch-size", default=1000, type=int)
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _rows(cursor) -> list[dict]:
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _line_row(cursor, row) -> dict:
    names = [column[0] for column in cursor.description]
    return dict(zip(names, row))


def _line_document(row: dict) -> dict:
    return {
        "line_id": str(row["LINE_ID"]),
        "invoice_no": vc(row["INVOICE_NO"]),
        "cust_id": vc(row["CUST_ID"]),
        "cust_no": vc(row["CUST_NO"]),
        "cust_name": vc(row["CUST_NAME"]),
        "tenant_id": vc(row["TENANT_ID"]),
        "line_no": int(row["LINE_NO"]),
        "line_type_cd": int(row["LINE_TYPE_CD"]),
        "item_desc": vc(row["ITEM_DESC"]),
        "qty": dec(row["QTY"], 3),
        "unit_price": dec(row["UNIT_PRICE"], 4),
        "amount": dec(row["AMOUNT"], 2),
        "tax_amt": dec(row["TAX_AMT"], 2),
        "invoice_dt": vc(row["INVOICE_DT"]),
        "service_period": vc(row["SERVICE_PERIOD"]),
        "posted_yn": ch(row["POSTED_YN"]),
        "gl_acct_csv": vc(row["GL_ACCT_CSV"]),
        "batch_no": int(row["BATCH_NO"]),
        "src_system": vc(row["SRC_SYSTEM"]),
    }


def _header_document(row: dict, lines: list[dict]) -> dict:
    return {
        "_id": str(row["INVOICE_ID"]),
        "invoice_no": vc(row["INVOICE_NO"]),
        "cust_id": vc(row["CUST_ID"]),
        "tenant_id": vc(row["TENANT_ID"]),
        "invoice_dt": vc(row["INVOICE_DT"]),
        "due_dt": vc(row["DUE_DT"]),
        "status_cd": int(row["STATUS_CD"]),
        "total_amt": dec(row["TOTAL_AMT"], 2),
        "batch_no": int(row["BATCH_NO"]),
        "lines": lines,
        "ns": NS_VALUE,
    }


def _insert_chunks(collection, documents: list[dict], batch_size: int) -> int:
    inserted = 0
    for start in range(0, len(documents), batch_size):
        result = collection.insert_many(
            documents[start : start + batch_size], ordered=False
        )
        inserted += len(result.inserted_ids)
    return inserted


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")
    if args.quarantine_db != QUARANTINE_DB:
        raise RuntimeError(f"--quarantine-db must be exactly {QUARANTINE_DB}")
    if args.batch_size < 1:
        raise RuntimeError("--batch-size must be positive")

    dsn_value = _secret_value(args.dsn_secret, "Oracle DSN secret")
    uri_value = _secret_value(args.uri_secret, "Mongo URI secret")
    try:
        user, password, dsn = dsn_value.split("/", 2)
    except ValueError as exc:
        raise RuntimeError(
            f"Oracle DSN secret '{args.dsn_secret}' must contain user/password/dsn"
        ) from exc
    if not user or not password or not dsn:
        raise RuntimeError(
            f"Oracle DSN secret '{args.dsn_secret}' must contain non-empty user/password/dsn"
        )

    import oracledb
    from pymongo import MongoClient

    started_at = datetime.now(timezone.utc).isoformat()
    oracle = oracledb.connect(user=user, password=password, dsn=dsn)
    client = MongoClient(uri_value)
    try:
        header_cursor = oracle.cursor()
        header_cursor.execute(HEADERS_SQL)
        headers = _rows(header_cursor)
        header_cursor.close()

        matched_cursor = oracle.cursor()
        matched_cursor.arraysize = 5000
        matched_cursor.execute(MATCHED_LINES_SQL)
        matched_lines_by_invoice: dict[object, list[dict]] = {}
        matched_line_count = 0
        for raw_row in matched_cursor:
            row = _line_row(matched_cursor, raw_row)
            matched_lines_by_invoice.setdefault(row["INVOICE_ID"], []).append(
                _line_document(row)
            )
            matched_line_count += 1
        matched_cursor.close()

        orphan_cursor = oracle.cursor()
        orphan_cursor.arraysize = 5000
        orphan_cursor.execute(ORPHAN_LINES_SQL)
        quarantined_rows = []
        quarantined_at = datetime.now(timezone.utc).isoformat()
        for raw_row in orphan_cursor:
            row = _line_row(orphan_cursor, raw_row)
            line = _line_document(row)
            quarantined_rows.append(
                {
                    **line,
                    "_id": str(row["LINE_ID"]),
                    "ns": NS_VALUE,
                    "unit": "U2",
                    "reason_class": "orphan_fk",
                    "source": {
                        "table": "INVOICE_LINE",
                        "key": {"LINE_ID": str(row["LINE_ID"])},
                        "invoice_id": str(row["INVOICE_ID"]),
                        "batch_no": int(row["BATCH_NO"]),
                    },
                    "quarantined_at": quarantined_at,
                }
            )
        orphan_cursor.close()

        count_cursor = oracle.cursor()
        count_cursor.execute(LINE_COUNT_SQL)
        source_line_count = int(count_cursor.fetchone()[0])
        count_cursor.close()

        invoice_documents = [
            _header_document(
                row, matched_lines_by_invoice.get(row["INVOICE_ID"], [])
            )
            for row in headers
        ]

        target = client[args.target_db]
        quarantine = client[args.quarantine_db]
        target.drop_collection(FEED_COLLECTION)
        quarantine.drop_collection(ORPHAN_COLLECTION)
        feed = target.create_collection(FEED_COLLECTION)
        orphan_collection = quarantine.create_collection(ORPHAN_COLLECTION)

        inserted = _insert_chunks(feed, invoice_documents, args.batch_size)
        orphan_inserted = _insert_chunks(
            orphan_collection, quarantined_rows, args.batch_size
        )
        feed.create_index("batch_no")
        feed.create_index("cust_id")

        docs_after = feed.count_documents({})
        ns_docs_after = feed.count_documents({"ns": NS_VALUE})
        orphan_docs_after = orphan_collection.count_documents({})
        orphan_ns_docs_after = orphan_collection.count_documents({"ns": NS_VALUE})
        embedded_lines = next(
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
        )["embedded_lines"]
        feed_indexes = [index["name"] for index in feed.list_indexes()]
        orphan_indexes = [index["name"] for index in orphan_collection.list_indexes()]

        if docs_after != len(headers) or docs_after != 18750:
            raise RuntimeError(
                f"invoice_feed: expected 18750 documents, found {docs_after}"
            )
        if ns_docs_after != 18750:
            raise RuntimeError(
                f"invoice_feed: expected 18750 namespace documents, found {ns_docs_after}"
            )
        if embedded_lines != matched_line_count or embedded_lines != 149963:
            raise RuntimeError(
                "invoice_feed: expected 149963 embedded lines, "
                f"found {embedded_lines}"
            )
        if orphan_docs_after != len(quarantined_rows) or orphan_docs_after != 37:
            raise RuntimeError(
                "invoice_feed_orphan_lines: expected 37 documents, "
                f"found {orphan_docs_after}"
            )
        if orphan_ns_docs_after != 37:
            raise RuntimeError(
                "invoice_feed_orphan_lines: expected 37 namespace documents, "
                f"found {orphan_ns_docs_after}"
            )
        if embedded_lines + orphan_docs_after != source_line_count:
            raise RuntimeError(
                f"line cardinality is unbalanced: {embedded_lines} + "
                f"{orphan_docs_after} != {source_line_count}"
            )
        if "batch_no_1" not in feed_indexes or "cust_id_1" not in feed_indexes:
            raise RuntimeError(
                f"invoice_feed: required indexes missing from {feed_indexes}"
            )

        finished_at = datetime.now(timezone.utc).isoformat()
        _write_report(
            Path(args.report),
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "target_db": args.target_db,
                "ns": NS_VALUE,
                "secret_names": {
                    "dsn": args.dsn_secret,
                    "uri": args.uri_secret,
                },
                "quarantine_db": args.quarantine_db,
                "collections": {
                    FEED_COLLECTION: {
                        "root_table": "INVOICE_HEADER",
                        "dropped": True,
                        "recreated": True,
                        "source_rows": len(headers),
                        "inserted": inserted,
                        "docs_after": docs_after,
                        "ns_docs_after": ns_docs_after,
                        "embedded_lines": embedded_lines,
                        "source_embedded_rows": matched_line_count,
                        "indexes": feed_indexes,
                    },
                    ORPHAN_COLLECTION: {
                        "source_table": "INVOICE_LINE",
                        "reason_class": "orphan_fk",
                        "dropped": True,
                        "recreated": True,
                        "source_rows": len(quarantined_rows),
                        "inserted": orphan_inserted,
                        "docs_after": orphan_docs_after,
                        "ns_docs_after": orphan_ns_docs_after,
                        "indexes": orphan_indexes,
                    },
                },
                "cardinality": {
                    "source_invoice_line_rows": source_line_count,
                    "embedded_lines": embedded_lines,
                    "quarantined": orphan_docs_after,
                    "total": embedded_lines + orphan_docs_after,
                    "balanced": embedded_lines + orphan_docs_after == source_line_count,
                },
            },
        )
        print(
            f"U2 load complete: db={args.target_db} quarantine_db={args.quarantine_db} "
            f"ns={NS_VALUE} invoice_feed={inserted} embedded_lines={embedded_lines} "
            f"orphan_lines={orphan_inserted}"
        )
        return 0
    finally:
        client.close()
        oracle.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
