"""Wave0 app-level query replay: Oracle vs Mongo result parity (U0 scope)."""
import os, json
import oracledb
from pymongo import MongoClient

src = oracledb.connect(user="ow_billing", password="ow_billing",
                       dsn="localhost:52521/FREEPDB1")
cur = src.cursor()
db = MongoClient(os.environ["MONGODB_ATLAS_URI"])["ow_tp_mongodb_032752"]
out = {}

# 1. fn_list_plans (pkg_plans 02_pkg_plans.sql:20-33): active plans,
#    tier decode, ORDER BY monthly_fee, code
cur.execute("""
  SELECT id, code, DECODE(tier_cd,1,'starter',2,'growth',3,'scale','UNKNOWN'),
         TO_CHAR(monthly_fee), included_units, TO_CHAR(overage_rate)
    FROM plans WHERE NVL(active_yn,'N')='Y' ORDER BY monthly_fee, code""")
ora = [tuple(r) for r in cur.fetchall()]
tiers = {1: "starter", 2: "growth", 3: "scale"}
mg = []
for d in db.plans.aggregate([
        {"$match": {"active_yn": "Y"}},
        {"$sort": {"monthly_fee": 1, "code": 1}}]):
    mg.append((d["_id"], d["code"], tiers.get(d["tier_cd"], "UNKNOWN"),
               str(d["monthly_fee"].to_decimal().normalize()),
               d["included_units"],
               str(d["overage_rate"].to_decimal().normalize())))
ora_n = [(a, b, c, str(__import__('decimal').Decimal(dd).normalize()), int(e),
          str(__import__('decimal').Decimal(f).normalize())) for a, b, c, dd, e, f in ora]
out["fn_list_plans"] = {"ora_rows": len(ora), "mongo_rows": len(mg),
                        "equal": ora_n == mg,
                        "ora": ora_n, "mongo": mg}

# 2. f_code_desc (pkg_ow_util 01_pkg_util.sql:34-45): decode every code pair
cur.execute("SELECT code_type, code_val, code_desc FROM codes")
pairs = cur.fetchall()
mism = []
for ct, cv, cd in pairs:
    d = db.codes.find_one({"_id": f"{ct}#{int(cv)}"})
    if d is None or d["code_desc"] != cd:
        mism.append((ct, int(cv)))
# also unknown-code behavior: f_code_desc returns no row -> app default
missing_lookup = db.codes.find_one({"_id": "INV_STATUS#9999"})
out["f_code_desc"] = {"pairs": len(pairs), "mismatches": mism,
                      "unknown_code_returns_none": missing_lookup is None}

# 3. reports.py STATUS_SQL decode arm: INV_STATUS lookup table parity
cur.execute("SELECT code_val, code_desc FROM codes WHERE code_type='INV_STATUS' ORDER BY code_val")
ora_inv = [(int(a), b) for a, b in cur.fetchall()]
mg_inv = [(d["code_val"], d["code_desc"]) for d in
          db.codes.find({"code_type": "INV_STATUS"}).sort("code_val", 1)]
out["status_sql_decode_table"] = {"equal": ora_inv == mg_inv, "ora": ora_inv, "mongo": mg_inv}

# 4. entitlement/dunning tenant-side join (fn_entitlement t.id = :tenant_id):
#    point lookups for all 69 tenants + status decode via TENANT_STATUS
cur.execute("SELECT id, name, tax_exempt_yn, status_cd FROM tenants")
bad = []
for tid, name, tx, st in cur.fetchall():
    d = db.tenants.find_one({"_id": tid})
    if (d is None or d["name"] != name or d["tax_exempt_yn"] != (tx.rstrip() if tx else tx)
            or d["status_cd"] != int(st)):
        bad.append(tid)
    else:
        dec = db.codes.find_one({"_id": f"TENANT_STATUS#{int(st)}"})
        cur2 = src.cursor()
        cur2.execute("SELECT code_desc FROM codes WHERE code_type='TENANT_STATUS' AND code_val=:1", [st])
        r = cur2.fetchone()
        if (r is None) != (dec is None) or (r and dec and r[0] != dec["code_desc"]):
            bad.append(tid + " (decode)")
out["tenant_point_lookup_and_decode"] = {"tenants": 69, "failures": bad}

print(json.dumps(out, indent=1, default=str))
