#!/usr/bin/env python3
"""Load the U6 dunning tables from the read-only Oracle billing fixture."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tp_mongo.rating_service import NS_VALUE, TARGET_DB, md5_uuid

UNIT_COLLECTIONS = ("notifications",)

DUNNING_ATTEMPTS_SQL = (
    "SELECT ID, TENANT_ID, INVOICE_ID, ATTEMPT_NO, SCHEDULED_FOR, STATUS_CD "
    "FROM DUNNING_ATTEMPTS ORDER BY INVOICE_ID, ATTEMPT_NO"
)
NOTIFICATIONS_SQL = (
    "SELECT ID, TENANT_ID, KIND_CD, SENT_AT FROM NOTIFICATIONS ORDER BY ID"
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
        default=str(REPO_ROOT / ".migration/recon/U6/load_report.json"),
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
        "dunning_attempts": _oracle_rows(conn, DUNNING_ATTEMPTS_SQL),
        "notifications": _oracle_rows(conn, NOTIFICATIONS_SQL),
    }


def _transform(rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
    attempts: list[dict] = []
    seen = set()
    for row in rows["dunning_attempts"]:
        invoice_id = str(row["INVOICE_ID"])
        attempt_no = num(row["ATTEMPT_NO"])
        key = (invoice_id, attempt_no)
        if key in seen:
            raise RuntimeError(
                "DUNNING_ATTEMPTS contains duplicate (INVOICE_ID, ATTEMPT_NO): "
                f"{invoice_id}, {attempt_no}"
            )
        seen.add(key)
        attempts.append(
            {
                "invoice_id": invoice_id,
                "attempt_no": attempt_no,
                "id": md5_uuid(invoice_id + str(attempt_no)),
                "tenant_id": vc(row["TENANT_ID"]),
                "scheduled_for": date_ms(row["SCHEDULED_FOR"]),
                "status_cd": num(row["STATUS_CD"]),
            }
        )
    attempts.sort(key=lambda row: (row["invoice_id"], row["attempt_no"]))
    notifications = [
        {
            "_id": str(row["ID"]),
            "tenant_id": vc(row["TENANT_ID"]),
            "kind_cd": num(row["KIND_CD"]),
            "sent_at": date_ms(row["SENT_AT"]),
            "ns": NS_VALUE,
        }
        for row in rows["notifications"]
    ]
    return {"dunning_attempts": attempts, "notifications": notifications}


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
        invoice_collection_names = db.list_collection_names()
        if "invoices" not in invoice_collection_names:
            raise RuntimeError("U5 invoices must be loaded first: invoices collection is missing")
        invoices = db["invoices"]
        invoice_ids = {
            document["_id"]
            for document in invoices.find({"ns": NS_VALUE}, {"_id": 1})
        }
        if not invoice_ids:
            raise RuntimeError("U5 invoices must be loaded first: invoices collection is empty")
        orphan_attempts = [
            row
            for row in documents["dunning_attempts"]
            if row["invoice_id"] not in invoice_ids
        ]
        if orphan_attempts:
            raise RuntimeError(
                "DUNNING_ATTEMPTS contains orphan rows: "
                + ", ".join(row["invoice_id"] for row in orphan_attempts)
            )

        attempts_by_invoice = {invoice_id: [] for invoice_id in invoice_ids}
        for attempt in documents["dunning_attempts"]:
            attempts_by_invoice[attempt["invoice_id"]].append(
                {
                    "attempt_no": attempt["attempt_no"],
                    "id": attempt["id"],
                    "tenant_id": attempt["tenant_id"],
                    "scheduled_for": attempt["scheduled_for"],
                    "status_cd": attempt["status_cd"],
                }
            )
        for attempts in attempts_by_invoice.values():
            attempts.sort(key=lambda attempt: attempt["attempt_no"])
        for invoice_id, attempts in attempts_by_invoice.items():
            result = invoices.update_one(
                {"_id": invoice_id, "ns": NS_VALUE},
                {"$set": {"dunning_attempts": attempts}},
            )
            if result.matched_count != 1:
                raise RuntimeError(f"invoice disappeared during U6 load: {invoice_id}")

        collection = db["notifications"]
        db.drop_collection("notifications")
        db.create_collection("notifications")
        if documents["notifications"]:
            inserted = collection.insert_many(documents["notifications"], ordered=True)
            inserted_count = len(inserted.inserted_ids)
        else:
            inserted_count = 0
        collection.create_index(
            [("tenant_id", 1), ("kind_cd", 1), ("sent_at", 1)], unique=True
        )
        docs_after = collection.count_documents({})
        ns_docs_after = collection.count_documents({"ns": NS_VALUE})
        indexes = [index["name"] for index in collection.list_indexes()]
        source_attempt_rows = len(rows["dunning_attempts"])
        embedded_after = sum(len(attempts) for attempts in attempts_by_invoice.values())
        if docs_after != len(rows["notifications"]) or ns_docs_after != len(
            rows["notifications"]
        ):
            raise RuntimeError("notifications count or namespace assertion failed")
        if embedded_after != source_attempt_rows:
            raise RuntimeError("embedded dunning_attempts count assertion failed")
        invoice_docs = list(invoices.find({"ns": NS_VALUE}, {"dunning_attempts": 1}))
        if len(invoice_docs) != len(invoice_ids) or any(
            "dunning_attempts" not in document for document in invoice_docs
        ):
            raise RuntimeError("every U5 invoice must have dunning_attempts")
        if (
            source_attempt_rows != 1
            or len(rows["notifications"]) != 1
            or len(invoice_ids) != 3
        ):
            raise RuntimeError(
                "U6 fixture counts must be 1 dunning attempt, 1 notification, and 3 invoices"
            )
        finished_at = datetime.now(timezone.utc).isoformat()
        collection_report = {
            "root_table": "NOTIFICATIONS",
            "dropped": True,
            "recreated": True,
            "source_rows": len(rows["notifications"]),
            "inserted": inserted_count,
            "docs_after": docs_after,
            "ns_docs_after": ns_docs_after,
            "indexes": indexes,
        }
        _write_report(
            Path(args.report),
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "target_db": args.target_db,
                "ns": NS_VALUE,
                "secret_names": {"dsn": args.dsn_secret, "uri": args.uri_secret},
                "collections": {
                    "notifications": collection_report,
                    "invoices": {
                        "root_table": "INVOICES",
                        "dropped": False,
                        "embedded_dunning_attempts_source_rows": source_attempt_rows,
                        "embedded_dunning_attempts_after": embedded_after,
                        "invoice_docs_after": len(invoice_docs),
                        "all_have_dunning_attempts": True,
                    },
                },
            },
        )
        print(
            f"U6 load complete: db={args.target_db} ns={NS_VALUE} "
            f"notifications={inserted_count} "
            f"embedded_attempts={embedded_after}"
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
