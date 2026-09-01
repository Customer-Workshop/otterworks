"""Wave0 independent adversarial probes: codes/tenants/plans/fixture_meta."""
import os, json
from collections import Counter
import oracledb
from pymongo import MongoClient
from decimal import Decimal

src = oracledb.connect(user="ow_billing", password="ow_billing",
                       dsn="localhost:52521/FREEPDB1")
cur = src.cursor()
mc = MongoClient(os.environ["MONGODB_ATLAS_URI"])
db = mc["ow_tp_mongodb_032752"]
qdb = mc["ow_tp_mongodb_032752_quarantine"]
out = {}

def q(sql):
    cur.execute(sql); return cur.fetchall()

# --- null/missing distributions per field ---
nulls = {}
for tbl, cols in {"TENANTS": ["NAME","TAX_EXEMPT_YN","STATUS_CD"],
                  "PLANS": ["CODE","TIER_CD","MONTHLY_FEE","INCLUDED_UNITS","OVERAGE_RATE","ACTIVE_YN"],
                  "CODES": ["CODE_TYPE","CODE_VAL","CODE_DESC"]}.items():
    coll = tbl.lower()
    for c in cols:
        s_null = q(f"SELECT COUNT(*) FROM {tbl} WHERE {c} IS NULL")[0][0]
        f = c.lower()
        t_null = db[coll].count_documents({f: None})
        t_missing = db[coll].count_documents({f: {"$exists": False}})
        nulls[f"{coll}.{f}"] = {"src_null": s_null, "tgt_null": t_null,
                                "tgt_missing": t_missing,
                                "ok": s_null == t_null and t_missing == 0}
out["null_missing"] = nulls

# --- duplicate keys ---
dups = {}
dups["tenants_src_dup_id"] = q("SELECT COUNT(*) FROM (SELECT ID FROM TENANTS GROUP BY ID HAVING COUNT(*)>1)")[0][0]
dups["plans_src_dup_id"] = q("SELECT COUNT(*) FROM (SELECT ID FROM PLANS GROUP BY ID HAVING COUNT(*)>1)")[0][0]
dups["codes_src_dup_composed"] = q("SELECT COUNT(*) FROM (SELECT CODE_TYPE||'#'||CODE_VAL FROM CODES GROUP BY CODE_TYPE||'#'||CODE_VAL HAVING COUNT(*)>1)")[0][0]
for c in ["tenants","plans","codes","fixture_meta"]:
    agg = list(db[c].aggregate([{"$group":{"_id":"$_id","n":{"$sum":1}}},{"$match":{"n":{"$gt":1}}}]))
    dups[f"{c}_tgt_dup__id"] = len(agg)
out["duplicates"] = dups

# --- min/max boundary docs (doc-level check of extremes) ---
bounds = {}
smin, smax = q("SELECT MIN(ID), MAX(ID) FROM TENANTS")[0]
for k, sid in [("min", smin), ("max", smax)]:
    row = q(f"SELECT ID, NAME, TAX_EXEMPT_YN, STATUS_CD FROM TENANTS WHERE ID='{sid}'")[0]
    d = db.tenants.find_one({"_id": sid})
    ok = (d is not None and d.get("name") == (row[1] if row[1] != '' else None)
          and d.get("tax_exempt_yn") == (row[2].rstrip() if row[2] else row[2])
          and d.get("status_cd") == int(row[3]))
    bounds[f"tenants_{k}_id"] = {"id": sid, "ok": bool(ok), "doc_found": d is not None}
# plans: full doc-level compare of all 3 rows incl Decimal128 aggregate-backing fields
prows = q("SELECT ID, CODE, TIER_CD, MONTHLY_FEE, INCLUDED_UNITS, OVERAGE_RATE, ACTIVE_YN FROM PLANS ORDER BY ID")
pok = True
for r in prows:
    d = db.plans.find_one({"_id": r[0]})
    if d is None: pok = False; continue
    if (d["code"] != r[1] or d["tier_cd"] != int(r[2])
        or Decimal(str(d["monthly_fee"].to_decimal())) != Decimal(str(r[3])).quantize(Decimal("0.01"))
        or d["included_units"] != int(r[4])
        or Decimal(str(d["overage_rate"].to_decimal())) != Decimal(str(r[5])).quantize(Decimal("0.000001"))
        or d["active_yn"] != (r[6].rstrip() if r[6] else r[6])):
        pok = False
bounds["plans_all3_doc_level"] = pok
out["boundaries"] = bounds

# --- spot doc-level: full codes value compare (32 rows) ---
srows = {f"{r[0]}#{int(r[1])}": (r[0], int(r[1]), r[2]) for r in
         q("SELECT CODE_TYPE, CODE_VAL, CODE_DESC FROM CODES")}
tdocs = {d["_id"]: d for d in db.codes.find()}
mism = [k for k in srows if k not in tdocs or
        (tdocs[k]["code_type"], tdocs[k]["code_val"], tdocs[k]["code_desc"]) != srows[k]]
extra = [k for k in tdocs if k not in srows]
out["codes_full_value_diff"] = {"src_n": len(srows), "tgt_n": len(tdocs),
                                "mismatch": mism, "extra": extra}

# --- ns field + stray fields ---
ns_bad = {c: db[c].count_documents({"ns": {"$ne": "mongo_032752"}}) for c in
          ["tenants","plans","codes","fixture_meta"]}
out["ns_field"] = ns_bad
expected_keys = {"tenants": {"_id","name","tax_exempt_yn","status_cd","ns"},
                 "plans": {"_id","code","tier_cd","monthly_fee","included_units","overage_rate","active_yn","ns"},
                 "codes": {"_id","code_type","code_val","code_desc","ns"},
                 "fixture_meta": {"_id","ns"}}
stray = {}
for c, exp in expected_keys.items():
    bad = 0
    for d in db[c].find():
        if set(d.keys()) != exp: bad += 1
    stray[c] = bad
out["stray_or_missing_fields"] = stray

# --- empty-collection / quarantine behavior ---
out["quarantine_collections"] = qdb.list_collection_names()
out["target_db_collections"] = sorted(db.list_collection_names())
out["fixture_meta_count"] = {"src": q("SELECT COUNT(*) FROM FIXTURE_META")[0][0],
                             "tgt": db.fixture_meta.count_documents({})}

# --- indexes promised by the spec (codes unique _id is implicit; check others exist) ---
out["indexes"] = {c: sorted(i["name"] for i in db[c].list_indexes()) for c in
                  ["tenants","plans","codes","fixture_meta"]}

# --- cross-unit consistency: tenants/plans/codes decode joins ---
# every distinct tenants.status_cd must decode via codes TENANT_STATUS; plans.tier_cd via PLAN_TIER
s_status = {int(r[0]) for r in q("SELECT DISTINCT STATUS_CD FROM TENANTS")}
t_status = set(db.tenants.distinct("status_cd"))
code_types = Counter(d["code_type"] for d in db.codes.find())
s_code_types = dict(q("SELECT CODE_TYPE, COUNT(*) FROM CODES GROUP BY CODE_TYPE"))
tenant_status_codes = {d["code_val"] for d in db.codes.find({"code_type": "TENANT_STATUS"})}
plan_tiers_t = set(db.plans.distinct("tier_cd"))
plan_tier_codes = {d["code_val"] for d in db.codes.find({"code_type": "PLAN_TIER"})}
out["cross_unit"] = {
    "tenant_status_distinct_equal": s_status == t_status,
    "tenant_status_all_decodable": sorted(t_status - tenant_status_codes),
    "plan_tier_all_decodable": sorted(plan_tiers_t - plan_tier_codes),
    "code_type_hist_src": s_code_types, "code_type_hist_tgt": dict(code_types),
}

print(json.dumps(out, indent=1, default=str))
