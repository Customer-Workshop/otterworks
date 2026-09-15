"""Wave 1 / U4-usage: usage_events and rating_periods into Atlas.

usage_events is a plain collection (Open item 2), keyed on the source UUID, with a
{tenantId, occurredAt} index and the $jsonSchema validator that stands in for
trg_usage_events_check. rating_periods embeds RATING_RESULTS as results[], keyed on the
result ID.

    python migrations/mongodb/usage/load_usage.py [--drop]

Reads Oracle read-only through ORACLE_BILLING_URI in one snapshot transaction; writes only
ow_billing_migration through MONGODB_ATLAS_URI. Mapping: .migration/03_mapping_spec.json
(version 1). The load converges on the source key set: a document whose source row has gone
is deleted, so a re-run leaves the target identical.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pymongo import ASCENDING, DESCENDING, ReplaceOne
from pymongo.errors import CollectionInvalid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import (  # noqa: E402
    decode, load_codes, money, mongo_db, oracle_connect, rows, utc,
)

COLLECTIONS = ("usage_events", "rating_periods")

USAGE_EVENTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["tenantId", "occurredAt", "units", "kind"],
        "properties": {
            "units": {"bsonType": ["long", "int"], "minimum": 1},
            "kind": {"enum": ["api", "storage", "compute"]},
        },
    }
}

INDEXES = {
    "usage_events": [({"tenantId": ASCENDING, "occurredAt": ASCENDING},
                      {"name": "tenantId_1_occurredAt_1"})],
    "rating_periods": [({"tenantId": ASCENDING, "periodStart": DESCENDING},
                        {"name": "tenantId_1_periodStart_-1"})],
}

VALIDATORS = {"usage_events": USAGE_EVENTS_VALIDATOR}


def build_usage_events(conn, codes):
    for r in rows(conn, "SELECT id, tenant_id, occurred_at, units, kind_cd "
                        "FROM usage_events ORDER BY id"):
        yield {"_id": r["ID"],
               "tenantId": r["TENANT_ID"],
               "occurredAt": utc(r["OCCURRED_AT"]),
               "units": int(r["UNITS"]),
               "kind": decode(codes, "USAGE_KIND", r["KIND_CD"])}


def build_rating_periods(conn, _codes):
    results: dict[str, list[dict]] = {}
    for r in rows(conn, "SELECT id, period_id, subscription_id, used_units, quota_units, "
                        "rollover_units, billable_units, overage_amount, created_at "
                        "FROM rating_results ORDER BY period_id, id"):
        results.setdefault(r["PERIOD_ID"], []).append({
            "id": r["ID"],
            "subscriptionId": r["SUBSCRIPTION_ID"],
            "usedUnits": int(r["USED_UNITS"]),
            "quotaUnits": int(r["QUOTA_UNITS"]),
            "rolloverUnits": int(r["ROLLOVER_UNITS"]),
            "billableUnits": int(r["BILLABLE_UNITS"]),
            "overageAmount": money(r["OVERAGE_AMOUNT"]),
            "createdAt": utc(r["CREATED_AT"]),
        })
    for r in rows(conn, "SELECT id, tenant_id, period_start, period_end "
                        "FROM rating_periods ORDER BY id"):
        yield {"_id": r["ID"],
               "tenantId": r["TENANT_ID"],
               "periodStart": utc(r["PERIOD_START"]),
               "periodEnd": utc(r["PERIOD_END"]),
               "results": results.get(r["ID"], [])}


BUILDERS = {"usage_events": build_usage_events, "rating_periods": build_rating_periods}


def apply_validator(db, name: str) -> None:
    validator = VALIDATORS.get(name)
    if validator is None:
        return
    try:
        db.create_collection(name, validator=validator)
    except CollectionInvalid:
        db.command("collMod", name, validator=validator)


def load(drop: bool = False) -> dict[str, int]:
    conn = oracle_connect()
    db = mongo_db()
    counts: dict[str, int] = {}
    try:
        codes = load_codes(conn)
        for name in COLLECTIONS:
            if drop:
                db[name].drop()
            apply_validator(db, name)
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
                    help="drop both collections first (a clean reload)")
    args = ap.parse_args()
    load(drop=args.drop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
