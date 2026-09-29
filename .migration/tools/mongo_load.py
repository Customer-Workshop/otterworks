"""Shared MongoDB load library for the OW_BILLING Oracle->Mongo migration.

No SQL lives here: every unit's Oracle statements are string literals written
inline at its own call sites (the write-scope guard requires it).
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import oracledb
from bson import Decimal128
from bson.int64 import Int64
from pymongo import MongoClient, ReplaceOne

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / ".migration" / "03_mapping_spec.json"
WAVE_PATH = REPO_ROOT / ".migration" / "waves" / "wave-1.json"
TARGET_DB = "ow_tp_mmp_live"

_MODE_ENVS = {
    "fixture": ("OW_TP_ORACLE_FIXTURE_DSN", "OW_TP_MMP_FIXTURE_URI"),
    "live": ("OW_TP_ORACLE_RO_DSN", "OW_TP_MMP_TARGET_URI"),
}

OMIT = object()


def load_spec():
    return json.loads(SPEC_PATH.read_text())


def load_wave():
    return json.loads(WAVE_PATH.read_text())


def coll_spec(spec, name):
    for coll in spec["collections"]:
        if coll["collection"] == name:
            return coll
    raise KeyError(f"collection {name} not in mapping spec")


def unit_write_targets(unit_id):
    for batch in load_wave()["batches"]:
        if batch["unit"] == unit_id:
            return set(batch["write_targets"])
    raise KeyError(f"unit {unit_id} not in wave plan")


def convert(value, field):
    if value is None:
        return OMIT
    bson_type = field["bson_type"]
    source_type = field.get("source_type", "")
    if bson_type == "string":
        if not isinstance(value, str):
            raise TypeError(f"{field['source']}: expected str, got {type(value).__name__}")
        text = value.rstrip(" ") if source_type.startswith("CHAR") else value
        return OMIT if text == "" else text
    if bson_type == "decimal":
        if isinstance(value, float) or not isinstance(value, (Decimal, int)):
            raise TypeError(
                f"{field['source']}: expected Decimal, got {type(value).__name__}"
            )
        return Decimal128(value)
    if bson_type == "int":
        if isinstance(value, float) or not isinstance(value, (Decimal, int)):
            raise TypeError(f"{field['source']}: expected int, got {type(value).__name__}")
        return int(value)
    if bson_type == "long":
        if isinstance(value, float) or not isinstance(value, (Decimal, int)):
            raise TypeError(f"{field['source']}: expected long, got {type(value).__name__}")
        return Int64(value)
    if bson_type == "date":
        if not isinstance(value, datetime):
            raise TypeError(
                f"{field['source']}: expected datetime, got {type(value).__name__}"
            )
        return value.replace(microsecond=value.microsecond // 1000 * 1000)
    raise ValueError(f"{field['source']}: unhandled bson_type {bson_type}")


def _key_fields(coll):
    """Map source key columns to their document location."""
    key = coll["key"]
    target = key["target"]
    targets = [target] if isinstance(target, str) else target
    return {s: t for s, t in zip(key["source"], targets)}


def _key_value(value):
    if isinstance(value, Decimal):
        return Int64(value)
    if isinstance(value, datetime):
        return value.replace(microsecond=value.microsecond // 1000 * 1000)
    return value


def _doc_key(coll, row, doc):
    key = coll["key"]
    target = key["target"]
    if isinstance(target, str):
        return {target: _key_value(row[key["source"][0]])}
    if "id_format" in coll:
        rendered = coll["id_format"]
        for src, tgt in zip(key["source"], target):
            rendered = rendered.replace(f"<{tgt}>", str(row[src]))
        return {"_id": rendered}
    return {s: _key_value(row[src]) for s, src in zip(target, key["source"])}


def build_root_docs(coll, rows, embeds=None):
    """Build documents for one collection.

    rows: list of dicts (UPPER source column -> value) for the root table.
    embeds: {array_path: child_rows} matching the spec's embeds.
    """
    embeds = embeds or {}
    key = coll["key"]
    mapped_root = set(key["source"]) | {f["source"] for f in coll["fields"]}
    docs = []
    for row in rows:
        extra = set(row) - mapped_root
        if extra:
            raise ValueError(
                f"{coll['collection']}: unmapped source columns {sorted(extra)}"
            )
        missing = [s for s in key["source"] if s not in row] + [
            f["source"] for f in coll["fields"] if f["source"] not in row
        ]
        if missing:
            raise ValueError(
                f"{coll['collection']}: spec columns missing from row {sorted(missing)}"
            )
        doc = _doc_key(coll, row, {})
        for field in coll["fields"]:
            value = convert(row.get(field["source"]), field)
            if value is not OMIT:
                doc[field["target"]] = value
        docs.append(doc)

    spec_embeds = {e["array_path"]: e for e in coll.get("embeds", [])}
    for array_path, embed in spec_embeds.items():
        child_rows = embeds.get(array_path)
        if child_rows is None:
            raise ValueError(
                f"{coll['collection']}: embed {array_path} declared in spec but no rows supplied"
            )
        mapped_child = (
            set(embed["parent_key"])
            | set(embed["key"]["source"])
            | {f["source"] for f in embed["fields"]}
            | set(embed.get("parent_columns_dropped", []))
            | {
                token.upper()
                for token in re.findall(r"[A-Za-z_]\w*", embed.get("child_where", ""))
            }
        )
        grouped = {}
        for child in child_rows:
            extra = set(child) - mapped_child
            if extra:
                raise ValueError(
                    f"{coll['collection']}.{array_path}: unmapped source columns {sorted(extra)}"
                )
            missing = [s for s in embed["parent_key"] if s not in child] + [
                f["source"] for f in embed["fields"] if f["source"] not in child
            ]
            if missing:
                raise ValueError(
                    f"{coll['collection']}.{array_path}: spec columns missing from row {sorted(missing)}"
                )
            grouped.setdefault(tuple(child[k] for k in embed["parent_key"]), []).append(
                child
            )
        parent_keys = set(embed["parent_ref"])
        for doc, row in zip(docs, rows):
            ref = tuple(row[k] for k in parent_keys)
            elements = []
            for child in sorted(
                grouped.get(ref, []),
                key=lambda c: tuple(
                    _element_sort_value(c, embed, ob) for ob in embed["order_by"]
                ),
            ):
                element = _doc_key(embed, child, {})
                for field in embed["fields"]:
                    value = convert(child.get(field["source"]), field)
                    if value is not OMIT:
                        element[field["target"]] = value
                elements.append(element)
            doc[array_path] = elements
        orphaned = set(grouped) - {
            tuple(row[k] for k in parent_keys) for row in rows
        }
        if orphaned:
            raise ValueError(
                f"{coll['collection']}.{array_path}: {len(orphaned)} child keys match no parent"
            )
    return docs


def _element_sort_value(child, embed, order_key):
    for src, tgt in _key_fields(embed).items():
        if tgt == order_key:
            return child[src]
    for field in embed["fields"]:
        if field["target"] == order_key:
            return child[field["source"]]
    raise ValueError(f"order_by {order_key} not resolvable for {embed['child_table']}")


def write_collection(db, coll_name, docs, indexes, allowed_targets):
    if db.name != TARGET_DB:
        raise ValueError(f"refusing target db {db.name!r}; only {TARGET_DB} allowed")
    if f"{TARGET_DB}.{coll_name}" not in allowed_targets:
        raise ValueError(
            f"{TARGET_DB}.{coll_name} not in the unit's wave-1 write_targets"
        )
    coll = db[coll_name]
    upserted = modified = matched = 0
    ids = []
    for start in range(0, len(docs), 1000):
        batch = docs[start : start + 1000]
        ids.extend(d["_id"] for d in batch)
        result = coll.bulk_write(
            [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in batch],
            ordered=False,
        )
        upserted += result.upserted_count
        modified += result.modified_count
        matched += result.matched_count
    loaded = set(ids)
    stale = [d["_id"] for d in coll.find({}, {"_id": 1}) if d["_id"] not in loaded]
    deleted = coll.delete_many({"_id": {"$in": stale}}).deleted_count if stale else 0
    for index in indexes or []:
        coll.create_index(
            list(index["keys"].items()),
            unique=index.get("unique", False),
            background=True,
        )
    return {
        "upserted": upserted,
        "modified": modified,
        "matched": matched,
        "deleted": deleted,
    }


def fetch_dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def connect_source(env_name):
    from recon.adapters import parse_oracle_secret

    oracledb.defaults.fetch_decimals = True
    user, password, dsn = parse_oracle_secret(os.environ[env_name])
    return oracledb.connect(user=user, password=password, dsn=dsn)


def connect_target(env_name):
    return MongoClient(os.environ[env_name])[TARGET_DB]


def resolve_mode(mode):
    if mode not in _MODE_ENVS:
        raise ValueError(f"mode must be one of {sorted(_MODE_ENVS)}")
    return _MODE_ENVS[mode]


def run_unit(unit_id, load_fn):
    """Shared CLI: --mode fixture|live. load_fn(cursor, db) -> stats dict."""
    parser = argparse.ArgumentParser(prog=f"{unit_id} load")
    parser.add_argument("--mode", required=True, choices=sorted(_MODE_ENVS))
    args = parser.parse_args()
    source_env, target_env = resolve_mode(args.mode)
    started = datetime.now(timezone.utc)
    allowed = unit_write_targets(unit_id)
    source = connect_source(source_env)
    try:
        cur = source.cursor()
        db = connect_target(target_env)
        stats = load_fn(cur, db, allowed)
    finally:
        source.close()
    finished = datetime.now(timezone.utc)
    record = {
        "unit": unit_id,
        "mode": args.mode,
        "started_utc": started.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "finished_utc": finished.isoformat(timespec="seconds").replace("+00:00", "Z"),
        **stats,
    }
    out_dir = REPO_ROOT / ".migration" / "recon" / unit_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"load-{args.mode}.json"
    if out.exists():
        out.replace(out_dir / f"load-{args.mode}-previous.json")
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"wrote": str(out), **record}, sort_keys=True))
    return record
