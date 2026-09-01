#!/usr/bin/env python3
"""Load the U3 subscription Oracle tables into the registered Mongo database."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
UNIT_COLLECTIONS = ("subscriptions", "subscriptions_hist")
INSERT_BATCH = 1000
REPO_ROOT = Path(__file__).resolve().parents[1].parent
MAPPING_SPEC = REPO_ROOT / ".migration/03_mapping_spec.json"


def vc(v):
    """VARCHAR2 to string with empty strings represented as null."""
    return None if v is None or v == "" else str(v)


def ch(v):
    """CHAR to rstripped string with empty strings represented as null."""
    if v is None:
        return None
    value = str(v).rstrip(" ")
    return None if value == "" else value


def num(v):
    """NUMBER to int."""
    return None if v is None else int(v)


def date_ms(v):
    """DATE to UTC BSON date truncated to milliseconds."""
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.replace(microsecond=(v.microsecond // 1000) * 1000)


def converter(field: dict):
    """Per-field converter built from the approved mapping type pair."""
    bson_type = field["bson_type"]
    source_type = field["source_type"]
    if bson_type == "string" and source_type == "VARCHAR2":
        return vc
    if bson_type == "string" and source_type == "CHAR":
        return ch
    if bson_type == "int" and source_type == "NUMBER(4,0)":
        return num
    if bson_type == "date" and source_type == "DATE":
        return date_ms
    raise RuntimeError(
        f"{field['source']}: unsupported mapping pair {source_type} -> {bson_type}"
    )


def _mapping_entries(spec_path: Path) -> dict[str, dict]:
    spec = json.loads(spec_path.read_text())
    by_name = {entry["collection"]: entry for entry in spec.get("collections", [])}
    missing = [name for name in UNIT_COLLECTIONS if name not in by_name]
    if missing:
        raise RuntimeError(
            f"mapping spec {spec_path} is missing U3 collection(s): {', '.join(missing)}"
        )
    return {name: by_name[name] for name in UNIT_COLLECTIONS}


def _plan(entry: dict) -> dict:
    """Oracle column list plus target field converters for one approved entry."""
    key_columns = entry["key"]["source"]
    if len(key_columns) != 1:
        raise RuntimeError(f"{entry['collection']}: expected a single-column key")
    fields = [
        {
            "source": field["source"],
            "target": field["target"],
            "convert": converter(field),
        }
        for field in entry["fields"]
    ]
    return {
        "collection": entry["collection"],
        "root_table": entry["root_table"],
        "key_column": key_columns[0],
        "key_target": entry["key"]["target"],
        "fields": fields,
        "columns": [key_columns[0]] + [field["source"] for field in entry["fields"]],
    }


def _select(plan: dict) -> str:
    return (
        f"SELECT {', '.join(plan['columns'])} FROM {plan['root_table']} "
        f"ORDER BY {plan['key_column']}"
    )


def _stream(conn, sql: str):
    cursor = conn.cursor()
    cursor.arraysize = INSERT_BATCH
    cursor.execute(sql)
    names = [column[0] for column in cursor.description]
    try:
        for row in cursor:
            yield dict(zip(names, row))
    finally:
        cursor.close()


def _document(row: dict, plan: dict) -> dict:
    key = row[plan["key_column"]]
    if plan["collection"] == "subscriptions_hist":
        key = num(key)
    document = {plan["key_target"]: key}
    for field in plan["fields"]:
        document[field["target"]] = field["convert"](row[field["source"]])
    document["ns"] = NS_VALUE
    return document


def _insert_batches(collection, documents: list[dict]) -> int:
    inserted = 0
    for start in range(0, len(documents), INSERT_BATCH):
        result = collection.insert_many(
            documents[start:start + INSERT_BATCH], ordered=True
        )
        inserted += len(result.inserted_ids)
    return inserted


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
    parser.add_argument("--mapping", default=str(MAPPING_SPEC), type=Path)
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U3/load_report.json"),
    )
    return parser.parse_args()


def _secret_value(name: str, description: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"{description} environment variable name '{name}' is not set")
    return os.environ[name]


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def main() -> int:
    args = _args()
    if args.target_db != TARGET_DB:
        raise RuntimeError(f"--target-db must be exactly {TARGET_DB}")
    if set(UNIT_COLLECTIONS) != {"subscriptions", "subscriptions_hist"}:
        raise RuntimeError("UNIT_COLLECTIONS does not match the registered U3 collections")

    entries = _mapping_entries(Path(args.mapping))
    plans = {name: _plan(entries[name]) for name in UNIT_COLLECTIONS}

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
        db = client[args.target_db]
        for collection_name in UNIT_COLLECTIONS:
            db.drop_collection(collection_name)
            db.create_collection(collection_name)

        collection_reports = {}
        for collection_name in UNIT_COLLECTIONS:
            plan = plans[collection_name]
            collection = db[collection_name]
            documents = []
            source_rows = 0
            inserted = 0
            for row in _stream(oracle, _select(plan)):
                source_rows += 1
                documents.append(_document(row, plan))
                if len(documents) >= INSERT_BATCH:
                    inserted += _insert_batches(collection, documents)
                    documents = []
            if documents:
                inserted += _insert_batches(collection, documents)

            indexes = []
            if collection_name == "subscriptions":
                indexes.append(collection.create_index([("tenant_id", 1), ("starts_on", 1)]))

            docs_after = collection.count_documents({})
            ns_docs_after = collection.count_documents({"ns": NS_VALUE})
            index_names = [index["name"] for index in collection.list_indexes()]
            if inserted != source_rows:
                raise RuntimeError(
                    f"{collection_name}: inserted {inserted} of {source_rows} source rows"
                )
            if docs_after != source_rows:
                raise RuntimeError(
                    f"{collection_name}: expected {source_rows} documents, found {docs_after}"
                )
            if ns_docs_after != source_rows:
                raise RuntimeError(
                    f"{collection_name}: expected {source_rows} namespace documents, "
                    f"found {ns_docs_after}"
                )
            if set(indexes) - set(index_names):
                raise RuntimeError(f"{collection_name}: requested indexes are missing")
            collection_reports[collection_name] = {
                "root_table": plan["root_table"],
                "dropped": True,
                "recreated": True,
                "source_rows": source_rows,
                "inserted": inserted,
                "docs_after": docs_after,
                "ns_docs_after": ns_docs_after,
                "indexes": index_names,
            }

        finished_at = datetime.now(timezone.utc).isoformat()
        _write_report(
            Path(args.report),
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "target_db": args.target_db,
                "ns": NS_VALUE,
                "mapping_version": json.loads(Path(args.mapping).read_text())["version"],
                "secret_names": {
                    "dsn": args.dsn_secret,
                    "uri": args.uri_secret,
                },
                "collections": collection_reports,
            },
        )
        print(
            f"U3 load complete: db={args.target_db} ns={NS_VALUE} "
            f"subscriptions={collection_reports['subscriptions']['inserted']} "
            f"subscriptions_hist={collection_reports['subscriptions_hist']['inserted']}"
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
