#!/usr/bin/env python3
"""Migrate OW_BILLING.CUSTOMER_MASTER + ENTITY_ATTR_VALUE into MongoDB `customers`.

    make mongo-customers-migrate NS=demo

The 155-column customer row plus its EAV attribute sprawl collapse into one
document per customer:

    _id               uuid5(ID_NAMESPACE, "<ns>:<CUST_ID>")   (never uuid4)
    customer_id       CUST_ID
    signup_dt         BSON date (dirty DD-MON-YY strings quarantined, not coerced)
    related_acct_ids  real BSON array (was a comma-separated VARCHAR2)
    promo_codes       real BSON array
    balances.*        Decimal128 money
    attributes.<NAME> folded ENTITY_ATTR_VALUE rows, names preserved verbatim
    legacy.*          the sparse repeating groups, emitted only when non-null

The run is idempotent by construction: deterministic ids + upserts, plus a
namespace-scoped reconciliation of documents whose source row is gone. A run
over an empty source set is a no-op: prior output is left untouched.
"""

import argparse
import json
import os
import sys

import oracledb
from pymongo import ASCENDING, MongoClient, ReplaceOne, UpdateOne

from schema import (CUSTOMERS_COLLECTION, CUSTOMER_INDEXES, EAV_TABLE,
                    LEGACY_COLUMNS, MODELLED_COLUMNS, QUARANTINE_COLLECTION,
                    QUARANTINE_INDEXES, SOURCE_TABLE, customers_validator,
                    database_name, quarantine_database_name,
                    quarantine_validator)
from transform import (build_attribute_entry, build_document, document_id,
                       quarantine_id)

NS_RE = "abcdefghijklmnopqrstuvwxyz0123456789_"


def namespace(value: str) -> str:
    if not value or any(c not in NS_RE for c in value):
        raise argparse.ArgumentTypeError(
            "namespace must be lowercase alphanumeric/underscore")
    return value


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ns", required=True, type=namespace)
    ap.add_argument("--mongo-uri", default=os.environ.get("TP_MONGODB_URI")
                    or os.environ.get("MONGODB_URI"))
    ap.add_argument("--oracle-host", default=os.environ.get("DB_HOST", "localhost"))
    ap.add_argument("--oracle-port", type=int,
                    default=int(os.environ.get("DB_PORT", "52521")))
    ap.add_argument("--oracle-service", default=os.environ.get("DB_SERVICE", "FREEPDB1"))
    ap.add_argument("--oracle-user", default=os.environ.get("DB_USER", "ow_billing"))
    ap.add_argument("--oracle-password",
                    default=os.environ.get("DB_PASSWORD", "ow_billing"))
    ap.add_argument("--batch-size", type=int, default=1000,
                    help="rows per extract/load batch (trigger granularity: per-batch)")
    ap.add_argument("--summary-out", help="write the run summary JSON to this path")
    args = ap.parse_args(argv)
    if not args.mongo_uri:
        ap.error("set TP_MONGODB_URI (or MONGODB_URI), or pass --mongo-uri")
    return args


def oracle_connect(args):
    oracledb.defaults.fetch_decimals = True
    return oracledb.connect(user=args.oracle_user, password=args.oracle_password,
                            host=args.oracle_host, port=args.oracle_port,
                            service_name=args.oracle_service)


def discover_batch_no(cur, ns: str):
    """The conversion batch that owns this namespace's slice of the estate."""
    # SUBSTR avoids treating namespace characters like `_` and `%` as wildcards.
    cur.execute("""SELECT DISTINCT conversion_batch_no FROM customer_master
                    WHERE SUBSTR(cust_no, 1, LENGTH(:prefix)) = :prefix""",
                prefix=f"{ns.upper()}-")
    batches = [int(r[0]) for r in cur.fetchall() if r[0] is not None]
    if len(batches) > 1:
        raise SystemExit(f"ambiguous namespace slice: batches {sorted(batches)}")
    return batches[0] if batches else None


def ensure_collection(db, name: str, validator: dict, indexes):
    if name in db.list_collection_names():
        db.command({"collMod": name, "validator": validator,
                    "validationLevel": "strict", "validationAction": "error"})
    else:
        db.create_collection(name, validator=validator, validationLevel="strict",
                             validationAction="error")
    for spec in indexes:
        db[name].create_index([(k, ASCENDING) for k, _ in spec["keys"]],
                              name=spec["name"], unique=spec.get("unique", False))


def check_source_columns(columns):
    """Refuse to run if the estate grew a column the target model does not know."""
    unknown = sorted(set(columns) - MODELLED_COLUMNS - set(LEGACY_COLUMNS))
    if unknown:
        raise SystemExit(
            f"{SOURCE_TABLE} has columns this migration does not map: {unknown}. "
            "Extend schema.LEGACY_COLUMNS (and the validator) before migrating; "
            "silently dropping a source column is not allowed.")


def load_customers(cur, ns, batch_no, customers, quarantine, batch_size):
    cur.execute("""SELECT * FROM customer_master WHERE conversion_batch_no = :b
                    ORDER BY cust_id""", b=batch_no)
    columns = [d[0].lower() for d in cur.description]
    check_source_columns(columns)
    stats = {"source_rows": 0, "documents": 0, "quarantined": 0, "batches": 0}
    migrated_ids, quarantine_ids = set(), set()
    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        stats["batches"] += 1
        cust_ops, quarantine_ops = [], []
        for row in rows:
            record = dict(zip(columns, row))
            stats["source_rows"] += 1
            doc, attributions = build_document(record, ns, batch_no)
            if doc is not None:
                migrated_ids.add(doc["_id"])
                cust_ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
            customer_id = record.get("cust_id") or "<unkeyed>"
            for attribution in attributions:
                qdoc = attribution.document(ns, customer_id, batch_no)
                quarantine_ids.add(qdoc["_id"])
                quarantine_ops.append(ReplaceOne({"_id": qdoc["_id"]}, qdoc, upsert=True))
        if cust_ops:
            customers.bulk_write(cust_ops, ordered=False)
            stats["documents"] += len(cust_ops)
        if quarantine_ops:
            quarantine.bulk_write(quarantine_ops, ordered=False)
            stats["quarantined"] += len(quarantine_ops)
    return stats, migrated_ids, quarantine_ids


def fold_attributes(cur, ns, batch_no, customers, quarantine, batch_size):
    """Fold every ENTITY_ATTR_VALUE row into its owning customer's document."""
    cur.execute("""SELECT e.entity_id, e.attr_name, e.attr_value, e.attr_type,
                          e.created_dt, e.eav_id
                     FROM entity_attr_value e
                     JOIN customer_master c ON c.cust_id = e.entity_id
                    WHERE e.entity_type = 'CUSTOMER'
                      AND c.conversion_batch_no = :b
                    ORDER BY e.entity_id, e.eav_id""", b=batch_no)
    stats = {"eav_rows": 0, "folded": 0, "customers_with_attributes": 0,
             "quarantined": 0}
    ops, quarantine_ops = [], []
    quarantine_ids = set()
    state = {"customer_id": None, "attributes": {}}

    def flush_customer():
        customer_id = state["customer_id"]
        if customer_id is None or not state["attributes"]:
            return
        ops.append(UpdateOne({"_id": document_id(ns, customer_id)},
                             {"$set": {"attributes": dict(state["attributes"])}}))
        stats["customers_with_attributes"] += 1

    def drain():
        if ops:
            customers.bulk_write(ops, ordered=False)
            ops.clear()
        if quarantine_ops:
            quarantine.bulk_write(quarantine_ops, ordered=False)
            quarantine_ops.clear()

    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break
        for entity_id, attr_name, attr_value, attr_type, created_dt, _eav_id in rows:
            stats["eav_rows"] += 1
            if entity_id != state["customer_id"]:
                flush_customer()
                state = {"customer_id": entity_id, "attributes": {}}
            entry, error = build_attribute_entry(attr_value, attr_type, created_dt)
            if error:
                stats["quarantined"] += 1
                qdoc = {
                    "_id": quarantine_id(ns, entity_id, error, attr_name),
                    "customer_id": entity_id,
                    "namespace": ns,
                    "reason": error,
                    "field": attr_name,
                    "detail": f"{EAV_TABLE} row for attribute {attr_name}",
                    "source": {"table": EAV_TABLE, "batch_no": int(batch_no)},
                }
                if entry and entry.get("raw_hex"):
                    qdoc["raw_hex"] = entry["raw_hex"]
                quarantine_ids.add(qdoc["_id"])
                quarantine_ops.append(ReplaceOne({"_id": qdoc["_id"]}, qdoc, upsert=True))
                continue
            state["attributes"].setdefault(attr_name, []).append(entry)
            stats["folded"] += 1
        if len(ops) >= batch_size:
            drain()
    flush_customer()
    drain()
    return stats, quarantine_ids


def reconcile(collection, ns, expected_ids):
    """Drop documents in this namespace that this run did not produce.

    Scoped to `namespace` so a rerun cannot touch another namespace's slice,
    and only reached when the source set is non-empty (an empty run exits
    before this point, leaving prior output untouched).
    """
    stale = [doc["_id"] for doc in collection.find({"namespace": ns}, {"_id": 1})
             if doc["_id"] not in expected_ids]
    if stale:
        return collection.delete_many({"_id": {"$in": stale}}).deleted_count
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    ns = args.ns
    conn = oracle_connect(args)
    cur = conn.cursor()
    cur.arraysize = args.batch_size

    batch_no = discover_batch_no(cur, ns)
    if batch_no is None:
        print(json.dumps({"namespace": ns, "action": "no-op",
                          "detail": f"no {SOURCE_TABLE} rows for namespace {ns}; "
                                    "prior output left untouched"}, indent=2))
        return 0

    client = MongoClient(args.mongo_uri, uuidRepresentation="standard")
    db = client[database_name(ns)]
    qdb = client[quarantine_database_name(ns)]
    ensure_collection(db, CUSTOMERS_COLLECTION, customers_validator(), CUSTOMER_INDEXES)
    ensure_collection(qdb, QUARANTINE_COLLECTION, quarantine_validator(),
                      QUARANTINE_INDEXES)
    customers = db[CUSTOMERS_COLLECTION]
    quarantine = qdb[QUARANTINE_COLLECTION]

    cust_stats, migrated_ids, quarantine_ids = load_customers(
        cur, ns, batch_no, customers, quarantine, args.batch_size)
    eav_stats, eav_quarantine_ids = fold_attributes(
        cur, ns, batch_no, customers, quarantine, args.batch_size)
    removed = reconcile(customers, ns, migrated_ids)
    quarantine_removed = reconcile(quarantine, ns, quarantine_ids | eav_quarantine_ids)

    summary = {
        "namespace": ns,
        "batch_no": batch_no,
        "source": {"table": SOURCE_TABLE, "eav_table": EAV_TABLE},
        "target": {
            "database": database_name(ns),
            "collection": CUSTOMERS_COLLECTION,
            "quarantine_database": quarantine_database_name(ns),
            "quarantine_collection": QUARANTINE_COLLECTION,
        },
        "customers": cust_stats,
        "attributes": eav_stats,
        "stale_documents_removed": removed,
        "stale_quarantine_removed": quarantine_removed,
        "documents_in_target": customers.count_documents({"namespace": ns}),
        "quarantine_in_target": quarantine.count_documents({"namespace": ns}),
    }
    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    if args.summary_out:
        with open(args.summary_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    client.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
