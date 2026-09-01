"""Wave 2 independent adversarial probes (U3/U4/U7). Read-only on both stacks.

Runs serially in the single live source window. Never calls PL/SQL that writes
(pkg_* log_msg is autonomous-txn INSERT); all Oracle access is plain SELECT.
"""
import json, os, sys
from collections import Counter
from decimal import Decimal

import oracledb
from pymongo import MongoClient
from bson.decimal128 import Decimal128

USER, PWD, DSN = os.environ["OW_BILLING_FIXTURE_DSN"].split("/", 2)
ora = oracledb.connect(user=USER, password=PWD, dsn=DSN)
cur = ora.cursor()
mc = MongoClient(os.environ["MONGODB_ATLAS_URI"])
db = mc["ow_tp_mongodb_032752"]
qdb = mc["ow_tp_mongodb_032752_quarantine"]
NS = {"ns": "mongo_032752"}
out = {}

def q(sql, **kw):
    cur.execute(sql, kw)
    return cur.fetchall()

def one(sql, **kw):
    return q(sql, **kw)[0][0]

# ---- collections inventory / ns / stray fields ----
out["target_collections"] = sorted(db.list_collection_names())
out["quarantine_collections"] = sorted(qdb.list_collection_names())
for c in ["subscriptions", "subscriptions_hist", "usage_events", "rating_periods",
          "rating_results", "billing_audit_log"]:
    total = db[c].count_documents({})
    out[f"{c}.count"] = total
    out[f"{c}.ns_ok"] = db[c].count_documents(NS) == total

# source counts (run twice for drift check)
src_tables = {"subscriptions": "SUBSCRIPTIONS", "subscriptions_hist": "SUBSCRIPTIONS_HIST",
              "usage_events": "USAGE_EVENTS", "rating_periods": "RATING_PERIODS",
              "rating_results": "RATING_RESULTS", "billing_audit_log": "BILLING_AUDIT_LOG"}
out["src_counts"] = {t: [one(f"select count(*) from {v}"), one(f"select count(*) from {v}")]
                     for t, v in src_tables.items()}

# ---- duplicate keys at source ----
out["dup_keys"] = {}
for t, k in [("SUBSCRIPTIONS", "ID"), ("USAGE_EVENTS", "ID"), ("RATING_PERIODS", "ID"),
             ("RATING_RESULTS", "ID")]:
    out["dup_keys"][t] = q(f"select {k} from {t} group by {k} having count(*)>1")

# duplicate natural keys guarded by unique constraints in spec
out["dup_rating_period_natural"] = q(
    "select tenant_id, period_start from RATING_PERIODS group by tenant_id, period_start having count(*)>1")

# ---- null/missing distributions per field ----
def null_probe(table, collection, cols):
    res = {}
    for col, fld in cols:
        src_nulls = one(f"select count(*) from {table} where {col} is null")
        tgt_null = db[collection].count_documents({fld: None, **NS})  # null or missing
        tgt_missing = db[collection].count_documents({fld: {"$exists": False}, **NS})
        res[fld] = {"src_null": src_nulls, "tgt_null_or_missing": tgt_null,
                    "tgt_missing": tgt_missing,
                    "ok": src_nulls == tgt_null and tgt_missing == 0}
    return res

def mapping_cols(path):
    m = json.load(open(path))
    return {c["collection"]: [(f["source"], f["target"]) for f in c["fields"]]
            for c in m["collections"]}

u3m = mapping_cols(os.path.expanduser("~/wave_recon/wt-u3/.migration/recon/U3/mapping/u3.json"))
u4m = mapping_cols(os.path.expanduser("~/wave_recon/wt-u4/.migration/recon/U4/mapping/u4.json"))
out["nulls.subscriptions"] = null_probe("SUBSCRIPTIONS", "subscriptions", u3m["subscriptions"])
out["nulls.usage_events"] = null_probe("USAGE_EVENTS", "usage_events", u4m["usage_events"])
out["nulls.rating_periods"] = null_probe("RATING_PERIODS", "rating_periods", u4m["rating_periods"])
out["nulls.rating_results"] = null_probe("RATING_RESULTS", "rating_results", u4m["rating_results"])

# ---- independent doc-level full compare (my own code, not the harness) ----
def canon_src(v, typ):
    if v is None: return None
    if isinstance(v, str):
        v = v.rstrip(" ") if typ == "CHAR" else v
        return None if v == "" else v
    return v

def canon_tgt(v):
    if isinstance(v, Decimal128): return v.to_decimal()
    return v

def full_compare(table, collection, cols, key_src, sample_sql=None, dec_cols=()):
    mismatches = []
    sel = ", ".join(c for c, _ in cols)
    sql = sample_sql or f"select {key_src}, {sel} from {table}"
    cur.execute(sql)
    colmeta = cur.description
    n = 0
    for row in cur.fetchall():
        n += 1
        key, vals = row[0], row[1:]
        doc = db[collection].find_one({"_id": key, **NS})
        if doc is None:
            mismatches.append((key, "MISSING_DOC")); continue
        for (srccol, tgt), v in zip(cols, vals):
            sv = canon_src(v, "CHAR")
            tv = canon_tgt(doc.get(tgt))
            if isinstance(sv, float): sv = Decimal(str(sv))
            if isinstance(tv, Decimal) and sv is not None: sv = Decimal(str(sv))
            if hasattr(sv, "tzinfo") and sv is not None and hasattr(tv, "tzinfo") and tv is not None:
                sv = sv.replace(tzinfo=None); tv = tv.replace(tzinfo=None)
            if sv != tv:
                mismatches.append((str(key), tgt, repr(sv), repr(tv)))
    return {"rows": n, "mismatches": mismatches[:20], "mismatch_count": len(mismatches)}

# exact decimal fetch: use TO_CHAR for NUMBER scaled columns to avoid float artifacts
oracledb.defaults.fetch_decimals = True
out["fullcmp.subscriptions"] = full_compare("SUBSCRIPTIONS", "subscriptions",
                                            u3m["subscriptions"], "ID")
out["fullcmp.rating_periods"] = full_compare("RATING_PERIODS", "rating_periods",
                                             u4m["rating_periods"], "ID")
out["fullcmp.rating_results"] = full_compare("RATING_RESULTS", "rating_results",
                                             u4m["rating_results"], "ID")
out["fullcmp.usage_events"] = full_compare("USAGE_EVENTS", "usage_events",
                                           u4m["usage_events"], "ID")

# ---- min/max boundary docs ----
out["boundary"] = {}
for t, c in [("SUBSCRIPTIONS", "subscriptions"), ("USAGE_EVENTS", "usage_events")]:
    lo, hi = one(f"select min(id) from {t}"), one(f"select max(id) from {t}")
    out["boundary"][c] = {"min": lo, "max": hi,
                          "min_doc_exists": db[c].find_one({"_id": lo}) is not None,
                          "max_doc_exists": db[c].find_one({"_id": hi}) is not None,
                          "tgt_min": db[c].find({}, {"_id": 1}).sort("_id", 1).limit(1)[0]["_id"],
                          "tgt_max": db[c].find({}, {"_id": 1}).sort("_id", -1).limit(1)[0]["_id"]}

# ---- aggregate cross-checks (sums of numerics, distincts) ----
def dec(x):
    return str(x) if x is not None else None
out["agg"] = {
    "usage_units_sum": [dec(one("select sum(units) from USAGE_EVENTS")),
                        dec(next(iter(db.usage_events.aggregate([{"$group": {"_id": None, "s": {"$sum": "$units"}}}])), {}).get("s"))],
    "overage_sum": [dec(one("select to_char(sum(overage_amount)) from RATING_RESULTS")),
                    dec(canon_tgt(next(iter(db.rating_results.aggregate([{"$group": {"_id": None, "s": {"$sum": "$overage_amount"}}}])), {}).get("s")))],
    "sub_status_hist": [sorted(map(tuple, q("select status_cd, count(*) from SUBSCRIPTIONS group by status_cd"))),
                        sorted((r["_id"], r["n"]) for r in db.subscriptions.aggregate([{"$group": {"_id": "$status_cd", "n": {"$sum": 1}}}]))],
    "usage_kind_hist": [sorted(map(tuple, q("select kind_cd, count(*) from USAGE_EVENTS group by kind_cd"))),
                        sorted((r["_id"], r["n"]) for r in db.usage_events.aggregate([{"$group": {"_id": "$kind_cd", "n": {"$sum": 1}}}]))],
}

# ---- all-NULL v1.2 amendment columns: ends_on / suspended_on ----
out["u3_amendment"] = {
    "src_ends_on_notnull": one("select count(*) from SUBSCRIPTIONS where ends_on is not null"),
    "src_suspended_notnull": one("select count(*) from SUBSCRIPTIONS where suspended_on is not null"),
    "tgt_ends_on_nonnull": db.subscriptions.count_documents({"ends_on": {"$ne": None}}),
    "tgt_ends_on_missing": db.subscriptions.count_documents({"ends_on": {"$exists": False}}),
    "tgt_susp_nonnull": db.subscriptions.count_documents({"suspended_on": {"$ne": None}}),
    "tgt_susp_missing": db.subscriptions.count_documents({"suspended_on": {"$exists": False}}),
}

# ---- stray fields ----
def field_universe(coll, allowed):
    rows = db[coll].aggregate([
        {"$project": {"kv": {"$objectToArray": "$$ROOT"}}},
        {"$unwind": "$kv"}, {"$group": {"_id": "$kv.k"}}])
    seen = sorted(r["_id"] for r in rows)
    return {"seen": seen, "stray": sorted(set(seen) - set(allowed))}
out["fields.subscriptions"] = field_universe("subscriptions",
    ["_id", "ns"] + [f for _, f in u3m["subscriptions"]])
out["fields.usage_events"] = field_universe("usage_events",
    ["_id", "ns"] + [f for _, f in u4m["usage_events"]])
out["fields.rating_results"] = field_universe("rating_results",
    ["_id", "ns"] + [f for _, f in u4m["rating_results"]])

# ---- indexes ----
out["indexes"] = {c: sorted(db[c].index_information().keys())
                  for c in ["subscriptions", "usage_events", "rating_periods",
                            "rating_results", "billing_audit_log", "subscriptions_hist"]}
out["ttl_index"] = {k: {kk: vv for kk, vv in v.items() if kk in ("key", "expireAfterSeconds")}
                    for k, v in db.billing_audit_log.index_information().items()}

# ---- cross-unit reference joins (both stacks) ----
out["xref"] = {
    "src_sub_tenant_orphans": one("select count(*) from SUBSCRIPTIONS s where not exists (select 1 from TENANTS t where t.id=s.tenant_id)"),
    "tgt_sub_tenant_orphans": len([s for s in db.subscriptions.find({}, {"tenant_id": 1})
                                   if db.tenants.find_one({"_id": s["tenant_id"]}) is None]),
    "src_sub_plan_orphans": one("select count(*) from SUBSCRIPTIONS s where s.plan_id is not null and not exists (select 1 from PLANS p where p.id=s.plan_id)"),
    "tgt_sub_plan_orphans": len([s for s in db.subscriptions.find({"plan_id": {"$ne": None}}, {"plan_id": 1})
                                 if db.plans.find_one({"_id": s["plan_id"]}) is None]),
    "src_ue_tenant_orphans": one("select count(*) from USAGE_EVENTS u where not exists (select 1 from TENANTS t where t.id=u.tenant_id)"),
    "tgt_ue_tenant_orphans": len({s["tenant_id"] for s in db.usage_events.find({}, {"tenant_id": 1})} -
                                 {t["_id"] for t in db.tenants.find({}, {"_id": 1})}),
    "src_rr_period_orphans": one("select count(*) from RATING_RESULTS r where not exists (select 1 from RATING_PERIODS p where p.id=r.period_id)"),
    "tgt_rr_period_orphans": len([r for r in db.rating_results.find({}, {"period_id": 1})
                                  if db.rating_periods.find_one({"_id": r["period_id"]}) is None]),
    "src_rr_sub_orphans": one("select count(*) from RATING_RESULTS r where r.subscription_id is not null and not exists (select 1 from SUBSCRIPTIONS s where s.id=r.subscription_id)"),
    "tgt_rr_sub_orphans": len([r for r in db.rating_results.find({"subscription_id": {"$ne": None}}, {"subscription_id": 1})
                               if db.subscriptions.find_one({"_id": r["subscription_id"]}) is None]),
    "sub_status_decodable": {
        "src": sorted(x[0] for x in q("select distinct status_cd from SUBSCRIPTIONS")),
        "tgt": sorted(db.subscriptions.distinct("status_cd")),
        "codes_SUB_STATUS": sorted(c["code_val"] for c in db.codes.find({"code_type": "SUB_STATUS"})),
    },
    "usage_kind_decodable": {
        "src": sorted(x[0] for x in q("select distinct kind_cd from USAGE_EVENTS")),
        "tgt": sorted(db.usage_events.distinct("kind_cd")),
        "codes_USAGE_KIND": sorted(c["code_val"] for c in db.codes.find({"code_type": "USAGE_KIND"})),
    },
}

json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
fails = []
def walk(prefix, v):
    if isinstance(v, dict):
        if "ok" in v and v["ok"] is False: fails.append(prefix)
        if "mismatch_count" in v and v["mismatch_count"]: fails.append(prefix)
        for k, vv in v.items(): walk(f"{prefix}.{k}", vv)
walk("", out)
print("FAILS:", fails)
