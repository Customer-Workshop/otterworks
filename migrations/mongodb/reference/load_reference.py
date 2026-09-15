"""Wave 0: reference data (plans, codes, tenants + embedded subscriptions, subscription_history).

Everything else in the migration depends on these four collections, so they land first
and alone. The load is idempotent: each document is replaced by its source primary key,
so re-running leaves the target identical.

    python migrations/mongodb/reference/load_reference.py [--drop]

Reads Oracle read-only through ORACLE_BILLING_URI; writes only ow_billing_migration
through MONGODB_ATLAS_URI. Mapping: .migration/03_mapping_spec.json (version 1).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pymongo import ASCENDING, DESCENDING, ReplaceOne

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.ow_mongo import (  # noqa: E402
    decode, load_codes, money, mongo_db, oracle_connect, parse_dt, rows, set_raw, utc, yn,
)

COLLECTIONS = ("plans", "codes", "tenants", "subscription_history")


def build_plans(conn, codes):
    for r in rows(conn, "SELECT id, code, tier_cd, monthly_fee, included_units, "
                        "overage_rate, active_yn FROM plans"):
        doc = {"_id": r["ID"],
               "code": r["CODE"],
               "tier": decode(codes, "PLAN_TIER", r["TIER_CD"]),
               "monthlyFee": money(r["MONTHLY_FEE"]),
               "includedUnits": int(r["INCLUDED_UNITS"]),
               "overageRate": money(r["OVERAGE_RATE"]),
               "active": yn(r["ACTIVE_YN"])}
        if doc["active"] is None:
            set_raw(doc, "legacy.activeYnRaw", r["ACTIVE_YN"])
        yield doc


def build_codes(conn, _codes):
    for r in rows(conn, "SELECT code_type, code_val, code_desc FROM codes"):
        yield {"_id": f"{r['CODE_TYPE']}:{int(r['CODE_VAL'])}",
               "codeType": r["CODE_TYPE"],
               "codeVal": int(r["CODE_VAL"]),
               "codeDesc": r["CODE_DESC"]}


def build_tenants(conn, codes):
    subs: dict[str, list[dict]] = {}
    for r in rows(conn, "SELECT id, tenant_id, plan_id, starts_on, ends_on, status_cd, "
                        "suspended_on FROM subscriptions ORDER BY tenant_id, id"):
        subs.setdefault(r["TENANT_ID"], []).append({
            "id": r["ID"],
            "planId": r["PLAN_ID"],
            "startsOn": utc(r["STARTS_ON"]),
            "endsOn": utc(r["ENDS_ON"]),
            "status": decode(codes, "SUB_STATUS", r["STATUS_CD"]),
            "suspendedOn": utc(r["SUSPENDED_ON"]),
        })
    for r in rows(conn, "SELECT id, name, tax_exempt_yn, status_cd FROM tenants"):
        doc = {"_id": r["ID"],
               "name": r["NAME"],
               "status": decode(codes, "TENANT_STATUS", r["STATUS_CD"]),
               "taxExempt": yn(r["TAX_EXEMPT_YN"]),
               "subscriptions": subs.get(r["ID"], [])}
        if doc["taxExempt"] is None:
            set_raw(doc, "legacy.taxExemptYnRaw", r["TAX_EXEMPT_YN"])
        yield doc


def build_subscription_history(conn, codes):
    for r in rows(conn, "SELECT hist_id, hist_dt, hist_op, id, tenant_id, plan_id, "
                        "starts_on, ends_on, status_cd, suspended_on FROM subscriptions_hist"):
        at = parse_dt(r["HIST_DT"])
        doc = {"_id": int(r["HIST_ID"]),
               "at": at,
               "op": r["HIST_OP"],
               "subscriptionId": r["ID"],
               "tenantId": r["TENANT_ID"],
               "planId": r["PLAN_ID"],
               "startsOn": utc(r["STARTS_ON"]),
               "endsOn": utc(r["ENDS_ON"]),
               "status": decode(codes, "SUB_STATUS", r["STATUS_CD"]),
               "suspendedOn": utc(r["SUSPENDED_ON"])}
        if at is None and r["HIST_DT"] is not None:
            set_raw(doc, "legacy.histDtRaw", r["HIST_DT"])
        yield doc


BUILDERS = {"plans": build_plans, "codes": build_codes, "tenants": build_tenants,
            "subscription_history": build_subscription_history}

INDEXES = {
    "plans": [({"code": ASCENDING}, {"unique": True, "name": "code_1"})],
    "codes": [({"codeType": ASCENDING, "codeVal": ASCENDING},
               {"unique": True, "name": "codeType_1_codeVal_1"})],
    "tenants": [({"name": ASCENDING}, {"unique": True, "name": "name_1"})],
    "subscription_history": [({"subscriptionId": ASCENDING, "at": DESCENDING},
                              {"name": "subscriptionId_1_at_-1"})],
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
            ops, n = [], 0
            for doc in BUILDERS[name](conn, codes):
                ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
                n += 1
                if len(ops) == 1000:
                    db[name].bulk_write(ops, ordered=False)
                    ops = []
            if ops:
                db[name].bulk_write(ops, ordered=False)
            for keys, opts in INDEXES[name]:
                db[name].create_index(list(keys.items()), **opts)
            counts[name] = n
            print(f"{name}: {n} documents")
    finally:
        conn.close()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drop", action="store_true",
                    help="drop the four collections first (a clean reload)")
    args = ap.parse_args()
    load(drop=args.drop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
