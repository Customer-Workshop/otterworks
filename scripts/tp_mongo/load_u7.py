#!/usr/bin/env python3
"""Load the U7 audit log from the read-only Oracle billing fixture."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from load_u0 import date_ms, vc

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
UNIT_COLLECTIONS = ("billing_audit_log",)
REPO_ROOT = Path(__file__).resolve().parents[1].parent
APP_DIR = REPO_ROOT / "services/legacy-billing/app"

AUDIT_SQL = (
    "SELECT LOG_ID, LOGGED_AT, MODULE, MESSAGE "
    "FROM BILLING_AUDIT_LOG ORDER BY LOG_ID"
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
        default=str(REPO_ROOT / ".migration/recon/U7/load_report.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _oracle_rows(conn) -> list[dict]:
    cursor = conn.cursor()
    try:
        cursor.execute(AUDIT_SQL)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def _transform(rows: list[dict]) -> list[dict]:
    return [
        {
            "_id": int(row["LOG_ID"]),
            "logged_at": date_ms(row["LOGGED_AT"]),
            "module": vc(row["MODULE"]),
            "message": vc(row["MESSAGE"]),
            "ns": NS_VALUE,
        }
        for row in rows
    ]


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def _ttl_spec(collection) -> dict:
    for index in collection.list_indexes():
        if index["name"] == "ttl_logged_at_90d":
            return {
                "name": index["name"],
                "key": dict(index["key"]),
                "expireAfterSeconds": index.get("expireAfterSeconds"),
            }
    raise RuntimeError("billing_audit_log: TTL index was not created")


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")
    if UNIT_COLLECTIONS != ("billing_audit_log",):
        raise RuntimeError("UNIT_COLLECTIONS does not match the registered U7 collection")

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

    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    import ow_util

    oracle = oracledb.connect(user=user, password=password, dsn=dsn)
    client = MongoClient(uri_value)
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        rows = _oracle_rows(oracle)
        documents = _transform(rows)
        db = client[args.target_db]
        collection_name = UNIT_COLLECTIONS[0]
        db.drop_collection(collection_name)
        collection = db.create_collection(collection_name)
        if documents:
            inserted = collection.insert_many(documents, ordered=True)
            inserted_count = len(inserted.inserted_ids)
        else:
            inserted_count = 0
        index_names = ow_util.ensure_audit_indexes(db)
        docs_after = collection.count_documents({})
        ns_docs_after = collection.count_documents({"ns": NS_VALUE})
        ttl_index = _ttl_spec(collection)
        if ttl_index["expireAfterSeconds"] != ow_util.AUDIT_TTL_SECONDS:
            raise RuntimeError(
                "billing_audit_log: TTL index has unexpected expireAfterSeconds"
            )
        expected = len(rows)
        if not (
            expected
            == inserted_count
            == docs_after
            == ns_docs_after
        ):
            raise RuntimeError(
                "billing_audit_log: source/inserted/target namespace counts differ"
            )
        collection_report = {
            "root_table": "BILLING_AUDIT_LOG",
            "dropped": True,
            "recreated": True,
            "source_rows": expected,
            "inserted": inserted_count,
            "docs_after": docs_after,
            "ns_docs_after": ns_docs_after,
            "indexes": index_names,
            "ttl_index": ttl_index,
        }
        _write_report(
            Path(args.report),
            {
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "target_db": args.target_db,
                "ns": NS_VALUE,
                "secret_names": {
                    "dsn": args.dsn_secret,
                    "uri": args.uri_secret,
                },
                "collections": {collection_name: collection_report},
            },
        )
        print(
            f"U7 load complete: db={args.target_db} ns={NS_VALUE} "
            f"billing_audit_log={inserted_count}"
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
