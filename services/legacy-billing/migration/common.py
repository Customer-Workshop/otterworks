"""Shared load helpers for the OW_BILLING -> mmp_rt_billing migration loaders.

Canonicalization follows .migration/03_mapping_spec.json `canonicalization.rules`
(profile: mongo-migration/profiles/oracle.md): CHAR rstrip, '' -> missing,
NUMBER(p,s>0) -> Decimal128, DATE/TIMESTAMP -> UTC datetime (ms), *_YN -> bool.
Secrets are read from the environment by NAME only.
"""
import json
import os
from datetime import date, datetime, time, timezone
from decimal import Decimal

import oracledb
from bson.decimal128 import Decimal128
from pymongo import MongoClient

SOURCE_SECRET = "ORACLE_BILLING_RO_DSN"
TARGET_SECRET = "MONGODB_MMP_RT_TARGET_URI"
TARGET_DB = "mmp_rt_billing"


def oracle_connect():
    raw = os.environ.get(SOURCE_SECRET)
    if not raw:
        raise SystemExit(f"{SOURCE_SECRET} is not set")
    cfg = json.loads(raw)
    return oracledb.connect(user=cfg["user"], password=cfg["password"], dsn=cfg["dsn"])


def mongo_db():
    uri = os.environ.get(TARGET_SECRET)
    if not uri:
        raise SystemExit(f"{TARGET_SECRET} is not set")
    return MongoClient(uri)[TARGET_DB]


def camel(name):
    parts = name.lower().split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def to_decimal(value):
    if value is None:
        return None
    return Decimal128(value if isinstance(value, Decimal) else Decimal(str(value)))


def to_utc(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=(value.microsecond // 1000) * 1000)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return value


def to_string(value, char=False):
    if value is None:
        return None
    if char:
        value = value.rstrip(" ")
    return None if value == "" else value


def yn_to_bool(value):
    if value is None:
        return None
    value = value.rstrip(" ")
    if value == "":
        return None
    return value.upper() == "Y"


def convert(field, value):
    """Convert one Oracle value per its mapping-spec field row."""
    if value is None:
        return None
    rules = field.get("rules", [])
    bson_type = field["bson_type"]
    if "yn_to_bool" in rules:
        return yn_to_bool(value)
    if bson_type == "decimal":
        return to_decimal(value)
    if bson_type == "date":
        return to_utc(value)
    if bson_type in ("int", "long"):
        return int(value)
    if bson_type == "string":
        return to_string(str(value) if not isinstance(value, str) else value,
                         char="rstrip_spaces" in rules)
    return value


def row_to_doc(fields, row):
    """Map one source row (dict keyed by column) to a document; NULL -> missing."""
    doc = {}
    for f in fields:
        v = convert(f, row.get(f["source"]))
        if v is not None:
            doc[f["target"]] = v
    return doc


def fetch_rows(conn, table, columns, where=None, arraysize=5000):
    """table is the mapping-spec root_table/child_table (schema-qualified, e.g. OW_BILLING.CODES)."""
    sql = f"SELECT {', '.join(columns)} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with conn.cursor() as cur:
        cur.arraysize = arraysize
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        for batch in iter(lambda: cur.fetchmany(arraysize), []):
            for row in batch:
                yield dict(zip(names, row))


def load_mapping(path):
    with open(path) as fh:
        return json.load(fh)


def parse_index(spec):
    """'{a:1, b:-1} unique' -> ([('a', 1), ('b', -1)], True)."""
    unique = spec.strip().endswith("unique")
    body = spec.strip().removesuffix("unique").strip().strip("{}")
    keys = []
    for part in body.split(","):
        name, direction = part.split(":")
        keys.append((name.strip(), int(direction)))
    return keys, unique


def reset_collection(db, name, index_plan=()):
    """Drop and recreate one declared write target with its planned indexes."""
    db.drop_collection(name)
    coll = db.create_collection(name)
    for spec in index_plan:
        keys, unique = parse_index(spec)
        coll.create_index(keys, unique=unique)
    return coll


def load_collection(conn, db, mapping, collection_name, where=None):
    """Load one root-only collection through its mapping-spec rows. Returns doc count."""
    c = next(x for x in mapping["collections"] if x["collection"] == collection_name)
    coll = reset_collection(db, collection_name, mapping.get("index_plan", {}).get(collection_name, []))
    key_src, key_tgt = c["key"]["source"], c["key"]["target"]
    cols = sorted({f["source"] for f in c["fields"]} | set(key_src))
    batch, n = [], 0
    for row in fetch_rows(conn, c["root_table"], cols, where or c.get("root_where")):
        doc = row_to_doc(c["fields"], row)
        if isinstance(key_tgt, str):
            doc[key_tgt] = row[key_src[0]] if key_tgt == "_id" else doc.get(key_tgt)
        else:
            doc["_id"] = {t: doc[t] for t in key_tgt}
        batch.append(doc)
        if len(batch) >= 2000:
            coll.insert_many(batch, ordered=False); n += len(batch); batch = []
    if batch:
        coll.insert_many(batch, ordered=False); n += len(batch)
    return n
