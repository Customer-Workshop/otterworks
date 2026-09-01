#!/usr/bin/env python3
"""Load the U1 customer Oracle tables into the registered Mongo database."""
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
UNIT_COLLECTIONS = ("customers", "customer_master_hist")
EMBED_ARRAY_PATH = "attributes"
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


def _number_scale(source_type: str) -> int:
    """Scale declared by a NUMBER(p,s) source type."""
    inside = source_type[source_type.index("(") + 1:source_type.index(")")]
    parts = [part.strip() for part in inside.split(",")]
    return int(parts[1]) if len(parts) == 2 else 0


def converter(field: dict):
    """Per-field converter built from the approved (bson_type, source_type) pair.

    Every converter maps a source NULL to None so the field is present in the
    document as an explicit BSON null (tolerances v1.0: NULL != missing).
    """
    bson_type = field["bson_type"]
    source_type = field["source_type"]
    if bson_type == "string" and source_type == "VARCHAR2":
        return vc
    if bson_type == "string" and source_type == "CHAR":
        return ch
    if bson_type == "int" and source_type in ("NUMBER(4,0)", "NUMBER(8,0)"):
        return lambda v: None if v is None else int(v)
    if bson_type == "long" and source_type == "NUMBER(12,0)":
        return lambda v: None if v is None else lng(v)
    if bson_type == "decimal" and source_type.startswith("NUMBER("):
        scale = _number_scale(source_type)
        return lambda v: None if v is None else dec(v, scale)
    if bson_type == "date" and source_type == "DATE":
        return lambda v: None if v is None else date_ms(v)
    raise RuntimeError(
        f"{field['source']}: unsupported mapping pair "
        f"(bson_type={bson_type}, source_type={source_type})"
    )


def _mapping_entries(spec_path: Path) -> dict[str, dict]:
    spec = json.loads(spec_path.read_text())
    by_name = {entry["collection"]: entry for entry in spec.get("collections", [])}
    missing = [name for name in UNIT_COLLECTIONS if name not in by_name]
    if missing:
        raise RuntimeError(
            f"mapping spec {spec_path} is missing U1 collection(s): {', '.join(missing)}"
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


def _embed_plan(entry: dict) -> dict:
    embeds = entry.get("embeds", [])
    if len(embeds) != 1 or embeds[0]["array_path"] != EMBED_ARRAY_PATH:
        raise RuntimeError(
            f"{entry['collection']}: expected exactly one '{EMBED_ARRAY_PATH}' embed"
        )
    embed = embeds[0]
    parent_key = embed["parent_key"]
    element_key = embed["key"]["source"]
    if len(parent_key) != 1 or len(element_key) != 1:
        raise RuntimeError("attributes embed: expected single-column parent and element keys")
    return {
        "array_path": embed["array_path"],
        "child_table": embed["child_table"],
        "child_where": embed["child_where"],
        "parent_column": parent_key[0],
        "key_column": element_key[0],
        "key_target": embed["key"]["target"],
        "fields": [
            {
                "source": field["source"],
                "target": field["target"],
                "convert": converter(field),
            }
            for field in embed["fields"]
        ],
    }


def _select(plan: dict) -> str:
    return (
        f"SELECT {', '.join(plan['columns'])} FROM {plan['root_table']} "
        f"ORDER BY {plan['key_column']}"
    )


def _embed_select(embed: dict) -> str:
    columns = [embed["key_column"], embed["parent_column"]] + [
        field["source"] for field in embed["fields"]
    ]
    return (
        f"SELECT {', '.join(columns)} FROM {embed['child_table']} "
        f"WHERE {embed['child_where']} "
        f"ORDER BY {embed['parent_column']}, {embed['key_column']}"
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
    document = {plan["key_target"]: row[plan["key_column"]]}
    for field in plan["fields"]:
        document[field["target"]] = field["convert"](row[field["source"]])
    return document


def _attributes(conn, embed: dict) -> tuple[dict[str, list[dict]], int]:
    grouped: dict[str, list[dict]] = {}
    source_rows = 0
    for row in _stream(conn, _embed_select(embed)):
        source_rows += 1
        element = {embed["key_target"]: lng(row[embed["key_column"]])}
        for field in embed["fields"]:
            element[field["target"]] = field["convert"](row[field["source"]])
        grouped.setdefault(row[embed["parent_column"]], []).append(element)
    for elements in grouped.values():
        elements.sort(key=lambda element: element[embed["key_target"]])
    return grouped, source_rows


def _insert_batches(collection, documents: list[dict]) -> int:
    inserted = 0
    for start in range(0, len(documents), INSERT_BATCH):
        result = collection.insert_many(
            documents[start:start + INSERT_BATCH], ordered=True
        )
        inserted += len(result.inserted_ids)
    return inserted


def _embedded_after(collection) -> tuple[int, int]:
    rows = list(
        collection.aggregate(
            [
                {"$project": {"size": {"$size": f"${EMBED_ARRAY_PATH}"}}},
                {
                    "$group": {
                        "_id": None,
                        "elements": {"$sum": "$size"},
                        "roots": {
                            "$sum": {"$cond": [{"$gt": ["$size", 0]}, 1, 0]}
                        },
                    }
                },
            ]
        )
    )
    if not rows:
        return 0, 0
    return int(rows[0]["elements"]), int(rows[0]["roots"])


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
    parser.add_argument("--mapping", default=str(MAPPING_SPEC), type=Path)
    parser.add_argument(
        "--report",
        default=str(REPO_ROOT / ".migration/recon/U1/load_report.json"),
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
    if set(UNIT_COLLECTIONS) != {"customers", "customer_master_hist"}:
        raise RuntimeError("UNIT_COLLECTIONS does not match the registered U1 collections")

    entries = _mapping_entries(Path(args.mapping))
    plans = {name: _plan(entries[name]) for name in UNIT_COLLECTIONS}
    embed = _embed_plan(entries["customers"])

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

        attributes, attribute_source_rows = _attributes(oracle, embed)
        collection_reports = {}
        for collection_name in UNIT_COLLECTIONS:
            plan = plans[collection_name]
            collection = db[collection_name]
            documents = []
            source_rows = 0
            inserted = 0
            roots_with_attributes = 0
            embedded_rows = 0
            for row in _stream(oracle, _select(plan)):
                source_rows += 1
                document = _document(row, plan)
                if collection_name == "customers":
                    elements = attributes.pop(document["_id"], [])
                    document[embed["array_path"]] = elements
                    if elements:
                        roots_with_attributes += 1
                        embedded_rows += len(elements)
                document["ns"] = NS_VALUE
                documents.append(document)
                if len(documents) >= INSERT_BATCH:
                    inserted += _insert_batches(collection, documents)
                    documents = []
            if documents:
                inserted += _insert_batches(collection, documents)

            if collection_name == "customers":
                if attributes:
                    orphans = sum(len(elements) for elements in attributes.values())
                    raise RuntimeError(
                        f"attributes embed: {orphans} child row(s) across "
                        f"{len(attributes)} ENTITY_ID(s) match no loaded customer"
                    )
                indexes = [
                    collection.create_index([("conversion_batch_no", 1)]),
                    collection.create_index([("tenant_id", 1)]),
                ]

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
            if collection_name == "customers":
                embedded_after, roots_after = _embedded_after(collection)
                if embedded_rows != attribute_source_rows:
                    raise RuntimeError(
                        f"attributes embed: embedded {embedded_rows} of "
                        f"{attribute_source_rows} child rows"
                    )
                if embedded_after != attribute_source_rows:
                    raise RuntimeError(
                        f"attributes embed: target holds {embedded_after} elements, "
                        f"source has {attribute_source_rows}"
                    )
                if roots_after != roots_with_attributes:
                    raise RuntimeError(
                        f"attributes embed: target has {roots_after} roots with "
                        f"attributes, load embedded {roots_with_attributes}"
                    )
                if set(indexes) - set(index_names):
                    raise RuntimeError("customers: requested indexes are missing")
                collection_reports[collection_name].update(
                    {
                        "embedded_attributes_source_rows": attribute_source_rows,
                        "embedded_attributes_after": embedded_after,
                        "roots_with_attributes": roots_after,
                    }
                )
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
        customers_report = collection_reports["customers"]
        print(
            f"U1 load complete: db={args.target_db} ns={NS_VALUE} "
            f"customers={customers_report['inserted']} "
            f"attributes={customers_report['embedded_attributes_after']} "
            f"customer_master_hist={collection_reports['customer_master_hist']['inserted']}"
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
