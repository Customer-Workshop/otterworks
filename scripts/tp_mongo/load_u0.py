#!/usr/bin/env python3
"""Load the U0 shared-reference Oracle tables into the registered Mongo database."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

from bson import Decimal128, Int64

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
UNIT_COLLECTIONS = ("codes", "tenants", "plans", "fixture_meta")
REPO_ROOT = Path(__file__).resolve().parents[1].parent


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


def lng(v):
    """NUMBER to BSON Int64."""
    return Int64(int(v))


def date_ms(v):
    """TIMESTAMP to UTC BSON date truncated to milliseconds."""
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.replace(microsecond=(v.microsecond // 1000) * 1000)


def _args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn-secret", default="OW_BILLING_FIXTURE_DSN",
        help="environment variable name containing user/password/dsn",
    )
    parser.add_argument(
        "--uri-secret", default="MONGODB_ATLAS_URI",
        help="environment variable name containing the Mongo URI",
    )
    parser.add_argument("--target-db", default=TARGET_DB)
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U0/load_report.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _oracle_rows(conn, sql: str) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _extract(conn) -> dict[str, list[dict]]:
    return {
        "tenants": _oracle_rows(
            conn,
            "SELECT ID, NAME, TAX_EXEMPT_YN, STATUS_CD "
            "FROM TENANTS ORDER BY ID",
        ),
        "plans": _oracle_rows(
            conn,
            "SELECT ID, CODE, TIER_CD, MONTHLY_FEE, INCLUDED_UNITS, "
            "OVERAGE_RATE, ACTIVE_YN FROM PLANS ORDER BY ID",
        ),
        "codes": _oracle_rows(
            conn,
            "SELECT CODE_TYPE, CODE_VAL, CODE_DESC "
            "FROM CODES ORDER BY CODE_TYPE, CODE_VAL",
        ),
        "fixture_meta": _oracle_rows(
            conn,
            "SELECT INITIALIZED_AT FROM FIXTURE_META",
        ),
    }


def _transform(rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {
        "tenants": [
            {
                "_id": row["ID"],
                "name": vc(row["NAME"]),
                "tax_exempt_yn": ch(row["TAX_EXEMPT_YN"]),
                "status_cd": int(row["STATUS_CD"]),
                "ns": NS_VALUE,
            }
            for row in rows["tenants"]
        ],
        "plans": [
            {
                "_id": row["ID"],
                "code": vc(row["CODE"]),
                "tier_cd": int(row["TIER_CD"]),
                "monthly_fee": dec(row["MONTHLY_FEE"], 2),
                "included_units": lng(row["INCLUDED_UNITS"]),
                "overage_rate": dec(row["OVERAGE_RATE"], 6),
                "active_yn": ch(row["ACTIVE_YN"]),
                "ns": NS_VALUE,
            }
            for row in rows["plans"]
        ],
        "codes": [
            {
                "_id": f"{row['CODE_TYPE']}#{int(row['CODE_VAL'])}",
                "code_type": vc(row["CODE_TYPE"]),
                "code_val": int(row["CODE_VAL"]),
                "code_desc": vc(row["CODE_DESC"]),
                "ns": NS_VALUE,
            }
            for row in rows["codes"]
        ],
        "fixture_meta": [
            {"_id": date_ms(row["INITIALIZED_AT"]), "ns": NS_VALUE}
            for row in rows["fixture_meta"]
        ],
    }


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")
    if set(UNIT_COLLECTIONS) != {"codes", "tenants", "plans", "fixture_meta"}:
        raise RuntimeError("UNIT_COLLECTIONS does not match the registered U0 collections")

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
            inserted = collection.insert_many(
                documents[collection_name], ordered=True
            )
            docs_after = collection.count_documents({})
            ns_docs_after = collection.count_documents({"ns": NS_VALUE})
            indexes = [index["name"] for index in collection.list_indexes()]
            if docs_after != len(rows[collection_name]):
                raise RuntimeError(
                    f"{collection_name}: expected {len(rows[collection_name])} documents, "
                    f"found {docs_after}"
                )
            if ns_docs_after != len(rows[collection_name]):
                raise RuntimeError(
                    f"{collection_name}: expected {len(rows[collection_name])} "
                    f"namespace documents, found {ns_docs_after}"
                )
            if collection_name == "codes" and "_id_" not in indexes:
                raise RuntimeError("codes: required _id_ index is missing")
            collection_reports[collection_name] = {
                "root_table": {
                    "codes": "CODES",
                    "tenants": "TENANTS",
                    "plans": "PLANS",
                    "fixture_meta": "FIXTURE_META",
                }[collection_name],
                "dropped": True,
                "recreated": True,
                "source_rows": len(rows[collection_name]),
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
                "secret_names": {
                    "dsn": args.dsn_secret,
                    "uri": args.uri_secret,
                },
                "collections": collection_reports,
            },
        )
        print(
            f"U0 load complete: db={args.target_db} ns={NS_VALUE} "
            f"codes={collection_reports['codes']['inserted']} "
            f"tenants={collection_reports['tenants']['inserted']} "
            f"plans={collection_reports['plans']['inserted']} "
            f"fixture_meta={collection_reports['fixture_meta']['inserted']}"
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
