"""Wave 1 / U5-ancillary: credit_notes, notifications and audit_log into Atlas.

Three small, independent collections. The load is idempotent: each document is replaced
by its source primary key, and a document whose source row has gone is deleted, so the
target converges on the source key set instead of keeping a ghost.

    python migrations/mongodb/ancillary/load_ancillary.py [--drop]

Reads Oracle read-only through ORACLE_BILLING_URI in one read-only transaction; writes
only ow_billing_migration through MONGODB_ATLAS_URI. Mapping:
.migration/03_mapping_spec.json (version 1).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pymongo import ASCENDING, ReplaceOne

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import (  # noqa: E402
    decode, load_codes, money, mongo_db, oracle_connect, rows, utc,
)

COLLECTIONS = ("credit_notes", "notifications", "audit_log")

AUDIT_LOG_TTL_SECONDS = 7776000  # 90 days, matching JOB_PURGE_AUDIT_LOG


def _text(value):
    """VARCHAR2 to string, with the empty string stored as null."""
    if value is None:
        return None
    return value or None


def build_credit_notes(conn, _codes):
    for r in rows(conn, "SELECT id, tenant_id, issued_on, amount, remaining_amount "
                        "FROM credit_notes"):
        yield {"_id": r["ID"],
               "tenantId": r["TENANT_ID"],
               "issuedOn": utc(r["ISSUED_ON"]),
               "amount": money(r["AMOUNT"]),
               "remainingAmount": money(r["REMAINING_AMOUNT"])}


def build_notifications(conn, codes):
    for r in rows(conn, "SELECT id, tenant_id, kind_cd, sent_at FROM notifications"):
        yield {"_id": r["ID"],
               "tenantId": r["TENANT_ID"],
               "kind": decode(codes, "NOTIF_KIND", r["KIND_CD"]),
               "sentAt": utc(r["SENT_AT"])}


def build_audit_log(conn, _codes):
    for r in rows(conn, "SELECT log_id, logged_at, module, message FROM billing_audit_log"):
        yield {"_id": int(r["LOG_ID"]),
               "loggedAt": utc(r["LOGGED_AT"]),
               "module": _text(r["MODULE"]),
               "message": _text(r["MESSAGE"])}


BUILDERS = {"credit_notes": build_credit_notes,
            "notifications": build_notifications,
            "audit_log": build_audit_log}

INDEXES = {
    "credit_notes": [({"tenantId": ASCENDING, "issuedOn": ASCENDING},
                      {"name": "tenantId_1_issuedOn_1"})],
    "notifications": [({"tenantId": ASCENDING, "kind": ASCENDING, "sentAt": ASCENDING},
                       {"unique": True, "name": "tenantId_1_kind_1_sentAt_1"})],
    "audit_log": [({"loggedAt": ASCENDING},
                   {"name": "loggedAt_1", "expireAfterSeconds": AUDIT_LOG_TTL_SECONDS})],
}


def load(drop: bool = False) -> dict[str, int]:
    conn = oracle_connect()
    db = mongo_db()
    counts = {}
    try:
        codes = load_codes(conn)
        for name in COLLECTIONS:
            if drop:
                db[name].drop()
            ops, n, seen = [], 0, set()
            for doc in BUILDERS[name](conn, codes):
                ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
                seen.add(doc["_id"])
                n += 1
                if len(ops) == 1000:
                    db[name].bulk_write(ops, ordered=False)
                    ops = []
            if ops:
                db[name].bulk_write(ops, ordered=False)
            stale = [i for i in db[name].distinct("_id") if i not in seen]
            if stale:
                db[name].delete_many({"_id": {"$in": stale}})
            for keys, opts in INDEXES[name]:
                db[name].create_index(list(keys.items()), **opts)
            counts[name] = n
            print(f"{name}: {n} documents"
                  + (f", {len(stale)} stale removed" if stale else ""))
    finally:
        conn.close()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drop", action="store_true",
                    help="drop the three collections first (a clean reload)")
    args = ap.parse_args()
    load(drop=args.drop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
