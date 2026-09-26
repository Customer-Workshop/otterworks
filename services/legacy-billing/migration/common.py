"""Shared load helpers for the OW_BILLING -> mmp_rt_billing migration loaders.

Canonicalization follows .migration/03_mapping_spec.json `canonicalization.rules`
(profile: mongo-migration/profiles/oracle.md): CHAR rstrip, '' -> missing,
NUMBER(p,s>0) -> Decimal128, DATE/TIMESTAMP -> UTC datetime (ms), *_YN -> bool.
Secrets are read from the environment by NAME only.
"""
import json
import os
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal

import oracledb
from bson.decimal128 import Decimal128
from pymongo import MongoClient, ReplaceOne

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


_SCALE_RE = re.compile(r"\(\s*\d+\s*,\s*(\d+)\s*\)")


def scale_of(source_type):
    """'NUMBER(12,2)' -> 2; unscaled/unknown -> None."""
    m = _SCALE_RE.search(source_type or "")
    return int(m.group(1)) if m else None


def to_decimal(value, scale=None):
    """oracledb hands NUMBER(p,s>0) back as float; go through str() so the value is the
    printed Oracle value, then quantize to the declared scale (half_even)."""
    if value is None:
        return None
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    if scale is not None:
        d = d.quantize(Decimal(1).scaleb(-scale))
    return Decimal128(d)


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
        return to_decimal(value, scale_of(field.get("source_type")))
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


def _root_doc(c, row):
    key_src, key_tgt = c["key"]["source"], c["key"]["target"]
    doc = row_to_doc(c["fields"], row)
    if isinstance(key_tgt, str):
        doc[key_tgt] = row[key_src[0]] if key_tgt == "_id" else doc.get(key_tgt)
    else:
        doc["_id"] = {t: doc[t] for t in key_tgt}
    return doc


def _flush(coll, batch):
    """Idempotent write: replace by _id (upsert) so a re-run over a live collection converges."""
    if batch:
        coll.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in batch], ordered=False)
    return len(batch)


def load_collection(conn, db, mapping, collection_name, where=None):
    """Load one root-only collection through its mapping-spec rows. Returns doc count."""
    c = next(x for x in mapping["collections"] if x["collection"] == collection_name)
    coll = reset_collection(db, collection_name, mapping.get("index_plan", {}).get(collection_name, []))
    cols = sorted({f["source"] for f in c["fields"]} | set(c["key"]["source"]))
    batch, n = [], 0
    for row in fetch_rows(conn, c["root_table"], cols, where or c.get("root_where")):
        batch.append(_root_doc(c, row))
        if len(batch) >= 2000:
            n += _flush(coll, batch); batch = []
    n += _flush(coll, batch)
    return n


def fetch_children(conn, embed, where=None):
    """Yield (parent_key_tuple, element_doc) for one mapping-spec embed (array shape).
    Elements are ordered by the element key so a document's array is deterministic."""
    cols = sorted({f["source"] for f in embed["fields"]} | set(embed["parent_key"]) | set(embed["key"]["source"]))
    sql_where = where or embed.get("child_where")
    order = ", ".join(embed["parent_key"] + embed["key"]["source"])
    sql = f"SELECT {', '.join(cols)} FROM {embed['child_table']}"
    if sql_where:
        sql += f" WHERE {sql_where}"
    sql += f" ORDER BY {order}"
    with conn.cursor() as cur:
        cur.arraysize = 5000
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        for batch in iter(lambda: cur.fetchmany(5000), []):
            for raw in batch:
                row = dict(zip(names, raw))
                yield tuple(row[k] for k in embed["parent_key"]), row_to_doc(embed["fields"], row)


def load_embedded_collection(conn, db, mapping, collection_name, where=None):
    """Load a root collection with its mapping-spec embeds (child tables -> arrays under
    array_path). Root docs get an empty array when no child row exists. Orphan child rows
    (no root row) are counted and returned, never written. Returns (doc count, orphans)."""
    c = next(x for x in mapping["collections"] if x["collection"] == collection_name)
    embeds = c.get("embeds", [])
    if not embeds:
        return load_collection(conn, db, mapping, collection_name, where), 0
    coll = reset_collection(db, collection_name, mapping.get("index_plan", {}).get(collection_name, []))
    cols = sorted({f["source"] for f in c["fields"]} | set(c["key"]["source"]))
    docs = {}
    for row in fetch_rows(conn, c["root_table"], cols, where or c.get("root_where")):
        doc = _root_doc(c, row)
        for e in embeds:
            doc[e["array_path"]] = []
        docs[tuple(row[k] for k in c["key"]["source"])] = doc
    orphans = 0
    for e in embeds:
        if e.get("shape", "array") != "array":
            raise ValueError(f"{collection_name}.{e['array_path']}: only array embeds are supported")
        for pk, elem in fetch_children(conn, e):
            parent = docs.get(pk)
            if parent is None:
                orphans += 1
                continue
            parent[e["array_path"]].append(elem)
    n, batch = 0, []
    for doc in docs.values():
        batch.append(doc)
        if len(batch) >= 2000:
            n += _flush(coll, batch); batch = []
    n += _flush(coll, batch)
    return n, orphans


def load_unit(conn, db, mapping, write_targets):
    """Load every declared write target of one unit mapping; embeds handled per spec."""
    results = {}
    for name in write_targets:
        n, orphans = load_embedded_collection(conn, db, mapping, name)
        results[name] = (n, orphans)
    return results
