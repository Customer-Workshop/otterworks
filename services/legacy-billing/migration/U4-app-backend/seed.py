"""Committed synthetic Mongo seed for the legacy-billing Mongo backend.

build: read the local synthetic Oracle fixture (OW_TP_ORACLE_FIXTURE_DSN, never
       the live secret) and write every map-1 collection the app reads, built
       with the shared .migration/tools/mongo_load converters, as xz-compressed
       canonical extended JSON (seed.jsonl.xz).
load:  drop and recreate ow_tp_mmp_live on a local fixture Mongo
       (OW_TP_MMP_FIXTURE_URI, 127.0.0.1/localhost only) from that seed.
"""

import argparse
import json
import lzma
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from bson import json_util
from bson.int64 import Int64
from pymongo import MongoClient

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
SEED_PATH = HERE / "seed.jsonl.xz"
TARGET_DB = "ow_tp_mmp_live"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "mongo-billing-fixture"}
JSON_OPTIONS = json_util.JSONOptions(json_mode=json_util.JSONMode.CANONICAL, tz_aware=False)


def _fixture_uri():
    uri = os.environ["OW_TP_MMP_FIXTURE_URI"]
    hosts = urlparse(uri).netloc.rsplit("@", 1)[-1].split(",")
    if any(host.rsplit(":", 1)[0].strip("[]") not in LOCAL_HOSTS for host in hosts):
        raise SystemExit("refusing a non-local Mongo target; the seed only loads the fixture")
    return uri


def _source_rows(cur):
    rows = {}
    cur.execute("SELECT * FROM ow_billing.customer_master")
    rows["CUSTOMER_MASTER"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.entity_attr_value WHERE entity_type = 'CUSTOMER'")
    rows["ENTITY_ATTR_VALUE"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.invoice_header")
    rows["INVOICE_HEADER"] = _fetch(cur)
    cur.execute(
        "SELECT * FROM ow_billing.invoice_line l WHERE EXISTS "
        "(SELECT 1 FROM ow_billing.invoice_header h WHERE h.invoice_id = l.invoice_id)"
    )
    rows["INVOICE_LINE"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.codes")
    rows["CODES"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.tenants")
    rows["TENANTS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.plans")
    rows["PLANS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.subscriptions")
    rows["SUBSCRIPTIONS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.subscriptions_hist")
    rows["SUBSCRIPTIONS_HIST"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.usage_events")
    rows["USAGE_EVENTS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.rating_periods")
    rows["RATING_PERIODS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.rating_results")
    rows["RATING_RESULTS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.invoices")
    rows["INVOICES"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.invoice_lines")
    rows["INVOICE_LINES"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.credit_notes")
    rows["CREDIT_NOTES"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.dunning_attempts")
    rows["DUNNING_ATTEMPTS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.notifications")
    rows["NOTIFICATIONS"] = _fetch(cur)
    cur.execute("SELECT * FROM ow_billing.billing_audit_log")
    rows["BILLING_AUDIT_LOG"] = _fetch(cur)
    cur.execute(
        "SELECT sequence_name, last_number FROM user_sequences "
        "WHERE sequence_name IN ('SEQ_BILLING_AUDIT_LOG', 'SEQ_SUBSCRIPTIONS_HIST')"
    )
    rows["SEQUENCES"] = _fetch(cur)
    return rows


def _fetch(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def build(out):
    sys.path.insert(0, str(REPO_ROOT / ".migration" / "tools"))
    import mongo_load

    dsn = os.environ["OW_TP_ORACLE_FIXTURE_DSN"]
    user, password, target = mongo_load.parse_oracle_secret(dsn)
    if not str(target).startswith(("localhost:", "127.0.0.1:")):
        raise SystemExit("refusing a non-local Oracle source; the seed is fixture-only")
    import oracledb

    oracledb.defaults.fetch_decimals = True
    connection = oracledb.connect(user=user, password=password, dsn=target)
    try:
        rows = _source_rows(connection.cursor())
    finally:
        connection.close()

    spec = mongo_load.load_spec()
    embeds = {
        "customers": {
            "attributes": [
                {key: value for key, value in row.items() if key != "ENTITY_TYPE"}
                for row in rows["ENTITY_ATTR_VALUE"]
            ]
        },
        "invoices": {"lines": rows["INVOICE_LINE"]},
        "billing_invoices": {"lines": rows["INVOICE_LINES"]},
    }
    collections = {}
    for coll in spec["collections"]:
        name = coll["collection"]
        table = coll["root_table"].split(".")[-1]
        if name == "quarantine_invoice_line":
            continue
        collections[name] = {
            "indexes": coll.get("indexes") or [],
            "docs": mongo_load.build_root_docs(coll, rows[table], embeds.get(name)),
        }
    collections["sequences"] = {
        "indexes": [],
        "docs": [
            {"_id": row["SEQUENCE_NAME"], "value": Int64(int(row["LAST_NUMBER"]) - 1)}
            for row in sorted(rows["SEQUENCES"], key=lambda row: row["SEQUENCE_NAME"])
        ],
    }
    with lzma.open(out, "wt", encoding="utf-8", preset=6) as handle:
        handle.write(json.dumps({"manifest": ".migration/fixtures/oracle-mmpfix.manifest.json",
                                 "target_db": TARGET_DB,
                                 "counts": {n: len(c["docs"]) for n, c in sorted(collections.items())}},
                                sort_keys=True) + "\n")
        for name in sorted(collections):
            handle.write(json.dumps({"collection": name, "indexes": collections[name]["indexes"]},
                                    sort_keys=True) + "\n")
            for doc in collections[name]["docs"]:
                handle.write(json.dumps({"c": name, "d": json.loads(json_util.dumps(doc, json_options=JSON_OPTIONS))},
                                        sort_keys=True) + "\n")
    print(json.dumps({n: len(c["docs"]) for n, c in sorted(collections.items())}, sort_keys=True))


def read_seed(path=SEED_PATH):
    collections = {}
    with lzma.open(path, "rt", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        for line in handle:
            record = json.loads(line)
            if "collection" in record:
                collections[record["collection"]] = {"indexes": record["indexes"], "docs": []}
            else:
                collections[record["c"]]["docs"].append(
                    json_util.loads(json.dumps(record["d"]), json_options=JSON_OPTIONS)
                )
    return header, collections


def load(uri, db_name=TARGET_DB, path=SEED_PATH):
    if db_name != TARGET_DB:
        raise SystemExit(f"refusing target db {db_name!r}; only {TARGET_DB} is declared")
    header, collections = read_seed(path)
    client = MongoClient(uri)
    try:
        client.drop_database(db_name)
        db = client[db_name]
        for name, coll in sorted(collections.items()):
            db.create_collection(name)
            for index in coll["indexes"]:
                db[name].create_index(list(index["keys"].items()), unique=bool(index.get("unique")))
            if coll["docs"]:
                db[name].insert_many(coll["docs"], ordered=False)
        counts = {name: db[name].count_documents({}) for name in sorted(collections)}
    finally:
        client.close()
    if counts != header["counts"]:
        raise SystemExit(f"seed load mismatch: {counts} != {header['counts']}")
    return counts


def main():
    parser = argparse.ArgumentParser(prog="U4-app-backend seed")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    sub.add_parser("load")
    args = parser.parse_args()
    if args.command == "build":
        build(SEED_PATH)
    else:
        print(json.dumps(load(_fixture_uri()), sort_keys=True))


if __name__ == "__main__":
    main()
