#!/usr/bin/env python3
"""Load the U4 rating tables from the read-only Oracle billing fixture."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

from bson import Decimal128, Int64

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
UNIT_COLLECTIONS = ("usage_events", "rating_periods", "rating_results")
REPO_ROOT = Path(__file__).resolve().parents[1].parent

USAGE_EVENTS_SQL = (
    "SELECT ID, TENANT_ID, OCCURRED_AT, UNITS, KIND_CD "
    "FROM USAGE_EVENTS ORDER BY ID"
)
RATING_PERIODS_SQL = (
    "SELECT ID, TENANT_ID, PERIOD_START, PERIOD_END "
    "FROM RATING_PERIODS ORDER BY ID"
)
RATING_RESULTS_SQL = (
    "SELECT ID, PERIOD_ID, SUBSCRIPTION_ID, USED_UNITS, QUOTA_UNITS, "
    "ROLLOVER_UNITS, BILLABLE_UNITS, OVERAGE_AMOUNT, CREATED_AT "
    "FROM RATING_RESULTS ORDER BY ID"
)


def vc(value):
    """VARCHAR2 to string with empty strings represented as null."""
    return None if value is None or value == "" else str(value)


def num(value):
    return None if value is None else Int64(int(value))


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
        default=str(REPO_ROOT / ".migration/recon/U4/load_report.json"),
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
        "usage_events": _oracle_rows(conn, USAGE_EVENTS_SQL),
        "rating_periods": _oracle_rows(conn, RATING_PERIODS_SQL),
        "rating_results": _oracle_rows(conn, RATING_RESULTS_SQL),
    }


def _transform(rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {
        "usage_events": [
            {
                "_id": str(row["ID"]),
                "tenant_id": vc(row["TENANT_ID"]),
                "occurred_at": date_ms(row["OCCURRED_AT"]),
                "units": num(row["UNITS"]),
                "kind_cd": int(row["KIND_CD"]),
                "ns": NS_VALUE,
            }
            for row in rows["usage_events"]
        ],
        "rating_periods": [
            {
                "_id": str(row["ID"]),
                "tenant_id": vc(row["TENANT_ID"]),
                "period_start": date_ms(row["PERIOD_START"]),
                "period_end": date_ms(row["PERIOD_END"]),
                "ns": NS_VALUE,
            }
            for row in rows["rating_periods"]
        ],
        "rating_results": [
            {
                "_id": str(row["ID"]),
                "period_id": vc(row["PERIOD_ID"]),
                "subscription_id": vc(row["SUBSCRIPTION_ID"]),
                "used_units": num(row["USED_UNITS"]),
                "quota_units": num(row["QUOTA_UNITS"]),
                "rollover_units": num(row["ROLLOVER_UNITS"]),
                "billable_units": num(row["BILLABLE_UNITS"]),
                "overage_amount": dec(row["OVERAGE_AMOUNT"], 2),
                "created_at": date_ms(row["CREATED_AT"]),
                "ns": NS_VALUE,
            }
            for row in rows["rating_results"]
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
            if collection_name == "usage_events":
                collection.create_index(
                    [("tenant_id", 1), ("occurred_at", 1), ("kind_cd", 1)]
                )
            elif collection_name == "rating_results":
                collection.create_index([("period_id", 1)])
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
                    "usage_events": "USAGE_EVENTS",
                    "rating_periods": "RATING_PERIODS",
                    "rating_results": "RATING_RESULTS",
                }[collection_name],
                "dropped": True,
                "recreated": True,
                "source_rows": source_rows,
                "inserted": len(inserted.inserted_ids),
                "docs_after": docs_after,
                "ns_docs_after": ns_docs_after,
                "indexes": indexes,
            }
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
            f"U4 load complete: db={args.target_db} ns={NS_VALUE} "
            f"usage_events={collection_reports['usage_events']['inserted']} "
            f"rating_periods={collection_reports['rating_periods']['inserted']} "
            f"rating_results={collection_reports['rating_results']['inserted']}"
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
