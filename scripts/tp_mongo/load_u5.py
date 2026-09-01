#!/usr/bin/env python3
"""Load the U5 invoicing tables from the read-only Oracle billing fixture."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

from bson import Decimal128

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
UNIT_COLLECTIONS = ("invoices", "credit_notes")
REPO_ROOT = Path(__file__).resolve().parents[1].parent

INVOICES_SQL = (
    "SELECT ID, TENANT_ID, PERIOD_ID, ISSUED_AT, SUBTOTAL, TAX, TOTAL, STATUS_CD "
    "FROM INVOICES ORDER BY ID"
)
INVOICE_LINES_SQL = (
    "SELECT ID, INVOICE_ID, LINE_NO, LINE_TYPE, DESCRIPTION, AMOUNT "
    "FROM INVOICE_LINES ORDER BY INVOICE_ID, LINE_NO"
)
CREDIT_NOTES_SQL = (
    "SELECT ID, TENANT_ID, ISSUED_ON, AMOUNT, REMAINING_AMOUNT "
    "FROM CREDIT_NOTES ORDER BY ID"
)


def vc(value):
    """VARCHAR2 to string with empty strings represented as null."""
    return None if value is None or value == "" else str(value)


def num(value):
    return None if value is None else int(value)


def date_ms(value):
    """DATE/TIMESTAMP to UTC BSON date truncated to milliseconds."""
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def dec(value, scale):
    """NUMBER to half-even rounded BSON Decimal128."""
    if value is None:
        return None
    return Decimal128(
        Decimal(str(value)).quantize(
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
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U5/load_report.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _oracle_rows(conn, sql: str) -> list[dict]:
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def _extract(conn) -> dict[str, list[dict]]:
    return {
        "invoices": _oracle_rows(conn, INVOICES_SQL),
        "invoice_lines": _oracle_rows(conn, INVOICE_LINES_SQL),
        "credit_notes": _oracle_rows(conn, CREDIT_NOTES_SQL),
    }


def _transform(rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
    invoice_ids = {str(row["ID"]) for row in rows["invoices"]}
    orphan_lines = [
        row for row in rows["invoice_lines"] if str(row["INVOICE_ID"]) not in invoice_ids
    ]
    if orphan_lines:
        raise RuntimeError(
            "INVOICE_LINES contains orphan rows: "
            + ", ".join(str(row["ID"]) for row in orphan_lines)
        )
    lines_by_invoice: dict[str, list[dict]] = {invoice_id: [] for invoice_id in invoice_ids}
    for row in rows["invoice_lines"]:
        lines_by_invoice[str(row["INVOICE_ID"])].append(
            {
                "line_no": int(row["LINE_NO"]),
                "id": vc(row["ID"]),
                "line_type": vc(row["LINE_TYPE"]),
                "description": vc(row["DESCRIPTION"]),
                "amount": dec(row["AMOUNT"], 2),
            }
        )
    for lines in lines_by_invoice.values():
        lines.sort(key=lambda line: line["line_no"])

    return {
        "invoices": [
            {
                "_id": str(row["ID"]),
                "tenant_id": vc(row["TENANT_ID"]),
                "period_id": vc(row["PERIOD_ID"]),
                "issued_at": date_ms(row["ISSUED_AT"]),
                "subtotal": dec(row["SUBTOTAL"], 2),
                "tax": dec(row["TAX"], 2),
                "total": dec(row["TOTAL"], 2),
                "status_cd": num(row["STATUS_CD"]),
                "ns": NS_VALUE,
                "lines": lines_by_invoice[str(row["ID"])],
            }
            for row in rows["invoices"]
        ],
        "credit_notes": [
            {
                "_id": str(row["ID"]),
                "tenant_id": vc(row["TENANT_ID"]),
                "issued_on": date_ms(row["ISSUED_ON"]),
                "amount": dec(row["AMOUNT"], 2),
                "remaining_amount": dec(row["REMAINING_AMOUNT"], 2),
                "ns": NS_VALUE,
            }
            for row in rows["credit_notes"]
        ],
    }


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")

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
        rows = _extract(oracle)
        documents = _transform(rows)
        db = client[args.target_db]
        collection_reports = {}
        for collection_name in UNIT_COLLECTIONS:
            collection = db[collection_name]
            db.drop_collection(collection_name)
            db.create_collection(collection_name)
            inserted = collection.insert_many(documents[collection_name], ordered=True)
            if collection_name == "invoices":
                collection.create_index(
                    [("tenant_id", 1), ("status_cd", 1), ("issued_at", 1)]
                )
            else:
                collection.create_index([("tenant_id", 1), ("issued_on", 1)])
            docs_after = collection.count_documents({})
            ns_docs_after = collection.count_documents({"ns": NS_VALUE})
            indexes = [index["name"] for index in collection.list_indexes()]
            source_rows = len(rows[collection_name])
            if docs_after != source_rows:
                raise RuntimeError(
                    f"{collection_name}: expected {source_rows} documents, found {docs_after}"
                )
            if ns_docs_after != source_rows:
                raise RuntimeError(
                    f"{collection_name}: expected {source_rows} namespace documents, "
                    f"found {ns_docs_after}"
                )
            collection_reports[collection_name] = {
                "root_table": {
                    "invoices": "INVOICES",
                    "credit_notes": "CREDIT_NOTES",
                }[collection_name],
                "dropped": True,
                "recreated": True,
                "source_rows": source_rows,
                "inserted": len(inserted.inserted_ids),
                "docs_after": docs_after,
                "ns_docs_after": ns_docs_after,
                "indexes": indexes,
            }
        collection_reports["invoices"]["embedded_lines_source_rows"] = len(
            rows["invoice_lines"]
        )
        collection_reports["invoices"]["embedded_lines_after"] = sum(
            len(document["lines"]) for document in documents["invoices"]
        )
        if collection_reports["invoices"]["embedded_lines_after"] != 2:
            raise RuntimeError("invoices: expected 2 embedded lines")
        if len(rows["invoices"]) != 3 or len(rows["credit_notes"]) != 5:
            raise RuntimeError("U5 fixture counts must be 3 invoices and 5 credit notes")
        finished_at = datetime.now(timezone.utc).isoformat()
        _write_report(
            Path(args.report),
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "target_db": args.target_db,
                "ns": NS_VALUE,
                "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
                "collections": collection_reports,
            },
        )
        print(
            f"U5 load complete: db={args.target_db} ns={NS_VALUE} "
            f"invoices={collection_reports['invoices']['inserted']} "
            f"embedded_lines={collection_reports['invoices']['embedded_lines_after']} "
            f"credit_notes={collection_reports['credit_notes']['inserted']}"
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
