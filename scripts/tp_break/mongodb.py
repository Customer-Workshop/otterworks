#!/usr/bin/env python3
"""Beat 4 "break the oracle" switch for the MongoDB demo track.

One command flips the beat, one command undoes it. The break mode attempts to
insert two legacy-shaped poison documents into a namespace's `customers`
collection — exactly the junk the Oracle estate happily stored for years:

  * a `DD-MON-YY` string date (`"31-FEB-24"`) where the contract wants a
    BSON date, and
  * a rogue 156th field (`tax_region_override`) that never earned a column
    and lived in the ENTITY_ATTR_VALUE dumping ground instead.

With an enforced `$jsonSchema` validator on the collection, both inserts
bounce with server error 121 (DocumentValidationFailure) — that rejection is
the demo. If a collection has no validator, the insert is accepted and the
script says so loudly (and exits non-zero): that is the legacy behavior the
migration removes.

Every poison document is tagged `tp_break_oracle: true` and has a
deterministic `_id`, so undo mode (`--undo`) deletes exactly the tagged
documents and nothing else. The switch never creates, drops, or reconfigures
collections and never touches the Atlas control plane — data-plane inserts
and tag-scoped deletes only.

Run via `make tp-break-oracle-mongodb NS=<ns> [UNDO=1|DRY_RUN=1|SELF_TEST=1]`.
The connection string comes from TP_MONGODB_URI (or MONGODB_URI); dry-run and
self-test need no cluster at all — self-test boots a throwaway local
`mongo:7` container, proves the reject/accept/undo paths, and removes it.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time

DOCUMENT_VALIDATION_FAILURE = 121
DUPLICATE_KEY = 11000
BREAK_TAG = "tp_break_oracle"

SELF_TEST_PORT = int(os.environ.get("TP_BREAK_SELFTEST_PORT", "57017"))
SELF_TEST_CONTAINER = "tp-break-oracle-selftest"

# Minimal customers contract mirroring the target model in
# docs/tech-partnerships/runbook-mongodb.md Beat 2 (used by --self-test only;
# real namespaces carry their own validator from the migration).
SELF_TEST_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "tenant_id", "cust_no", "name", "signup_at"],
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "string"},
            "tenant_id": {"bsonType": "string"},
            "cust_no": {"bsonType": "string"},
            "name": {"bsonType": "string"},
            "signup_at": {"bsonType": "date"},
            "attributes": {"bsonType": "object"},
            BREAK_TAG: {"bsonType": "bool"},
            "tp_break_case": {"bsonType": "string"},
        },
    }
}


def poison_docs(ns: str) -> list[dict]:
    """Deterministic legacy-shaped documents the validator must reject."""
    return [
        {
            "_id": f"tp-break-{ns}-dd-mon-yy-date",
            BREAK_TAG: True,
            "tp_break_case": "dd-mon-yy-date",
            "tenant_id": f"tp-break-{ns}",
            "cust_no": f"{ns.upper()}-99999901",
            "name": "Poison Otter (string date)",
            # VARCHAR2(9) 'DD-MON-YY' — and not even a real day.
            "signup_at": "31-FEB-24",
        },
        {
            "_id": f"tp-break-{ns}-rogue-156th-field",
            BREAK_TAG: True,
            "tp_break_case": "rogue-156th-field",
            "tenant_id": f"tp-break-{ns}",
            "cust_no": f"{ns.upper()}-99999902",
            "name": "Poison Otter (rogue field)",
            # A perfectly valid date: the ONLY violation is the rogue field.
            "signup_at": datetime.datetime(2024, 1, 1,
                                           tzinfo=datetime.timezone.utc),
            # The ad-hoc EAV attribute, smuggled in as column #156.
            "tax_region_override": "see ticket 48213",
        },
    ]


def undo_filter() -> dict:
    return {BREAK_TAG: True}


def hr(char: str = "-") -> None:
    print(char * 72)


def resolve_uri() -> str:
    uri = os.environ.get("TP_MONGODB_URI") or os.environ.get("MONGODB_URI")
    if not uri:
        print("ERROR: set TP_MONGODB_URI (or MONGODB_URI) to the target "
              "cluster connection string.", file=sys.stderr)
        raise SystemExit(2)
    return uri


def run_break(collection, ns: str) -> int:
    from pymongo.errors import WriteError

    rejected = 0
    accepted = 0
    for doc in poison_docs(ns):
        case = doc["tp_break_case"]
        try:
            collection.insert_one(doc)
        except WriteError as exc:
            if exc.code == DUPLICATE_KEY:
                accepted += 1
                print(f"[ACCEPTED] {case}: already present from an earlier run "
                      "— poison persisted (run UNDO=1 first)!")
                continue
            if exc.code != DOCUMENT_VALIDATION_FAILURE:
                raise
            rejected += 1
            print(f"[REJECTED] {case}: server error 121 "
                  "(DocumentValidationFailure)")
            details = (exc.details or {}).get("errInfo", {})
            if details:
                print(f"           errInfo: "
                      f"{json.dumps(details, default=str)[:400]}")
        else:
            accepted += 1
            print(f"[ACCEPTED] {case}: NO VALIDATOR REJECTED THIS DOCUMENT — "
                  "poison persisted!")
    hr()
    if accepted:
        print(f"{accepted} poison document(s) went straight in — this "
              "collection has no enforced")
        print("$jsonSchema (the legacy behavior). Clean up with UNDO=1.")
        return 1
    print(f"All {rejected} poison documents bounced at the door: the "
          "$jsonSchema contract holds.")
    print("(Nothing was written; UNDO=1 is a no-op but always safe.)")
    return 0


def run_undo(collection) -> int:
    result = collection.delete_many(undo_filter())
    print(f"[UNDO] removed {result.deleted_count} tagged poison document(s) "
          f"(filter {undo_filter()})")
    return 0


def run_dry_run(ns: str, db_name: str, coll_name: str, undo: bool) -> int:
    print(f"[DRY-RUN] target: db={db_name} collection={coll_name} "
          f"(no connection made)")
    if undo:
        print(f"[DRY-RUN] would delete_many({json.dumps(undo_filter())})")
        return 0
    for doc in poison_docs(ns):
        print("[DRY-RUN] would insert_one:")
        print(json.dumps(doc, indent=2, default=str))
    print("[DRY-RUN] expected demo outcome: both inserts rejected with "
          "server error 121.")
    return 0


def docker(*argv: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *argv], check=check,
                          capture_output=True, text=True)


def run_self_test() -> int:
    """Prove the reject, accept, and undo paths against a throwaway mongod."""
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    ns = "selftest"
    print(f"[self-test] starting throwaway mongo:7 on "
          f"127.0.0.1:{SELF_TEST_PORT} ...")
    docker("rm", "-f", SELF_TEST_CONTAINER, check=False)
    docker("run", "-d", "--rm", "--name", SELF_TEST_CONTAINER,
           "-p", f"127.0.0.1:{SELF_TEST_PORT}:27017", "mongo:7")
    try:
        client = MongoClient(f"mongodb://127.0.0.1:{SELF_TEST_PORT}",
                             serverSelectionTimeoutMS=2000)
        for _ in range(60):
            try:
                client.admin.command("ping")
                break
            except PyMongoError:
                time.sleep(1)
        else:
            print("[self-test] FAIL: mongod never became reachable",
                  file=sys.stderr)
            return 1

        db = client[f"ow_tp_{ns}"]
        db.create_collection("customers", validator=SELF_TEST_VALIDATOR,
                             validationLevel="strict",
                             validationAction="error")
        db.create_collection("customers_unvalidated")

        print("[self-test] 1/3 validated collection must reject both "
              "poison docs")
        if run_break(db["customers"], ns) != 0:
            print("[self-test] FAIL: validated collection accepted poison",
                  file=sys.stderr)
            return 1

        print("[self-test] 2/3 unvalidated collection must accept them "
              "(legacy behavior)")
        if run_break(db["customers_unvalidated"], ns) != 1:
            print("[self-test] FAIL: expected unvalidated collection to "
                  "accept poison", file=sys.stderr)
            return 1

        print("[self-test] 3/3 undo must remove exactly the tagged documents")
        db["customers_unvalidated"].insert_one(
            {"_id": "innocent-bystander", "tenant_id": "t", "cust_no": "c",
             "name": "keep me"})
        run_undo(db["customers_unvalidated"])
        remaining = list(db["customers_unvalidated"].find({}, {"_id": 1}))
        if remaining != [{"_id": "innocent-bystander"}]:
            print(f"[self-test] FAIL: unexpected survivors {remaining}",
                  file=sys.stderr)
            return 1

        print("[self-test] PASS: reject, accept, and undo paths all behave")
        return 0
    finally:
        docker("rm", "-f", SELF_TEST_CONTAINER, check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ns", help="target namespace, e.g. demo")
    ap.add_argument("--db", help="database name (default ow_tp_<ns>)")
    ap.add_argument("--collection", default="customers",
                    help="collection to poison (default customers)")
    ap.add_argument("--undo", action="store_true",
                    help="remove previously inserted poison documents")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would happen; no connection made")
    ap.add_argument("--self-test", action="store_true",
                    help="prove reject/accept/undo against a throwaway "
                         "local mongod")
    args = ap.parse_args()

    if args.self_test:
        return run_self_test()
    if not args.ns:
        ap.error("--ns is required (except with --self-test)")
    db_name = args.db or f"ow_tp_{args.ns}"

    if args.dry_run:
        return run_dry_run(args.ns, db_name, args.collection, args.undo)

    from pymongo import MongoClient

    client = MongoClient(resolve_uri(), serverSelectionTimeoutMS=10000)
    db = client[db_name]
    if args.collection not in db.list_collection_names():
        print(f"ERROR: collection {db_name}.{args.collection} does not exist "
              "on the target cluster.", file=sys.stderr)
        print("Nothing was written (a wrong --ns would otherwise create a "
              "brand-new empty database).", file=sys.stderr)
        return 2
    collection = db[args.collection]
    if args.undo:
        return run_undo(collection)
    return run_break(collection, args.ns)


if __name__ == "__main__":
    sys.exit(main())
