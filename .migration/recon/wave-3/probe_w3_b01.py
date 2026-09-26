"""Wave-3 independent probes for w3-b01 (u-07 util, u-08 plans). Mongo-side
behavioural probes on the fixture baseline + read-only Oracle function calls.
Writes only ow_billing_migration spec collections (reloaded from fixture after)."""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.expanduser("~/ow-b01/services/legacy-billing/migration/mongo"))
import oracledb, pymongo
import ow_util, plans_service as ps
import fixture_load as fl

db = pymongo.MongoClient(os.environ["MONGO_LOCAL_URI"])["ow_billing_migration"]
conn = fl._oracle_connect("OW_BILLING_FIXTURE_DSN")
cur = conn.cursor()
out = []
def probe(name, ok, detail):
    out.append({"probe": name, "result": "PASS" if ok else "FAIL", "detail": detail})

def reload():
    fl.load_baseline(conn, db)

reload()
EFF = dt.date(2027, 6, 1)

# P1 TRG_SUB_NO_UNCANCEL: open cancelled sub stays 30 through change_plan; open suspended -> 10 (DECODE(20,..,10))
canc = db["subscriptions"].find_one({"statusCd": 30, "endsOn": None})
synthetic = False
if canc is None:  # fixture has no open cancelled sub: synthesise one in the (disposable) Mongo fixture copy
    canc = db["subscriptions"].find_one({"statusCd": 10, "endsOn": None})
    db["subscriptions"].update_one({"_id": canc["_id"]}, {"$set": {"statusCd": 30}})
    canc["statusCd"] = 30; synthetic = True
susp = db["subscriptions"].find_one({"statusCd": 20, "endsOn": None})
res = {}
for label, sub in (("cancelled", canc), ("suspended", susp)):
    if sub is None:
        res[label] = "no open sub in fixture"; continue
    plan = db["plans"].find_one({"_id": {"$ne": sub["planId"]}})
    ps.change_plan(db, sub["tenantId"], plan["_id"], EFF)
    after = db["subscriptions"].find_one({"_id": sub["_id"]})
    new = db["subscriptions"].find_one({"_id": ow_util.md5_uuid(sub["tenantId"] + plan["_id"] + EFF.isoformat())})
    res[label] = {"synthetic_cancel": synthetic if label=="cancelled" else False, "old_status": sub["statusCd"], "after_status": after["statusCd"],
                  "after_endsOn": after["endsOn"].date().isoformat(), "new_sub_status": new["statusCd"] if new else None}
ok = (res["cancelled"] != "no open sub in fixture" and res["cancelled"]["after_status"] == 30
      and res["cancelled"]["after_endsOn"] == "2027-05-31" and res["cancelled"]["new_sub_status"] == 10
      and (res["suspended"] == "no open sub in fixture" or res["suspended"]["after_status"] == 10))
probe("P1 TRG_SUB_NO_UNCANCEL: cancelled never reopens on change_plan; suspended->active per DECODE", ok, res)

# P2 TRG_SUBSCRIPTIONS_HIST: exactly one UPD hist row per closed sub, full OLD copy, ids monotonic
reload()
tenant = db["subscriptions"].find_one({"endsOn": None, "statusCd": 10})["tenantId"]
before = list(db["subscriptions"].find({"tenantId": tenant, "endsOn": None, "startsOn": {"$lt": ps._utc(EFF)}}))
plan = db["plans"].find_one()
ps.change_plan(db, tenant, plan["_id"], EFF)
hist = list(db["subscriptionsHist"].find(sort=[("_id", 1)]))
byid = {h["id"]: h for h in hist}
full_copy = all(byid[b["_id"]]["statusCd"] == b["statusCd"] and byid[b["_id"]]["startsOn"] == b["startsOn"]
                and byid[b["_id"]].get("endsOn") is None and byid[b["_id"]]["histOp"] == "UPD" for b in before)
# second change_plan closes the new sub too -> one more hist row
ps.change_plan(db, tenant, plan["_id"], EFF + dt.timedelta(days=40))
hist2 = list(db["subscriptionsHist"].find(sort=[("_id", 1)]))
ids = [h["_id"] for h in hist2]
ok = len(hist) == len(before) >= 1 and full_copy and len(hist2) == len(before) + 1 and ids == list(range(1, len(ids) + 1))
probe("P2 TRG_SUBSCRIPTIONS_HIST: one UPD row per closed sub, OLD copy, monotonic hist_id", ok,
      {"closed": len(before), "hist_after_1st": len(hist), "hist_after_2nd": len(hist2), "ids": ids, "full_old_copy": full_copy})

# P3 duplicate change_plan (same tenant/plan/date) -> deterministic id collision must raise like ORA-00001
reload()
try:
    ps.change_plan(db, tenant, plan["_id"], EFF)
    ps.change_plan(db, tenant, plan["_id"], EFF)
    dup = "no error"
except pymongo.errors.DuplicateKeyError:
    dup = "DuplicateKeyError"
probe("P3 replayed change_plan with identical args raises duplicate-key (Oracle PK ORA-00001 equivalent)", dup == "DuplicateKeyError", {"outcome": dup})

# P4 entitlement boundaries: inclusive on endsOn, exclusive day before startsOn, none for unknown tenant
reload()
s = db["subscriptions"].find_one({"endsOn": {"$ne": None}})
if s is None:  # fixture has only open subs: close one via change_plan first
    o = db["subscriptions"].find_one({"endsOn": None, "statusCd": 10})
    ps.change_plan(db, o["tenantId"], plan["_id"], EFF)
    s = db["subscriptions"].find_one({"_id": o["_id"]})
e_on_end = ps.entitlement(db, s["tenantId"], s["endsOn"].date())
e_after = ps.entitlement(db, s["tenantId"], s["endsOn"].date() + dt.timedelta(days=1))
e_before = ps.entitlement(db, s["tenantId"], s["startsOn"].date() - dt.timedelta(days=1))
later = db["subscriptions"].find_one({"tenantId": s["tenantId"], "startsOn": {"$gt": s["endsOn"]}})
unknown = ps.entitlement(db, "no-such-tenant", EFF)
ok = (len(e_on_end) == 1 and e_on_end[0]["effective_on"] == s["endsOn"].date().isoformat()
      and (later is not None or e_after == []) and unknown == [])
probe("P4 fn_entitlement boundaries (endsOn inclusive, GREATEST effective_on, unknown tenant -> empty)", ok,
      {"on_end": e_on_end, "day_after_empty_or_later_sub": later is not None or e_after == [], "day_before": e_before, "unknown": unknown})

# P5 u-07 util edge inputs vs Oracle read-only functions
checks = {}
for s_ in ["", "x", "ünïcødé", "a" * 300]:
    o = cur.callfunc("pkg_ow_util.f_md5_uuid", oracledb.DB_TYPE_VARCHAR, [s_])
    checks[f"md5_uuid(len={len(s_)})"] = (o == ow_util.md5_uuid(s_))
o = cur.callfunc("pkg_ow_util.f_dt2str", oracledb.DB_TYPE_VARCHAR, [None])
checks["dt2str(NULL)"] = (o == ow_util.dt2str(None))
o = cur.callfunc("pkg_ow_util.f_str2dt", oracledb.DB_TYPE_DATE, [None])
checks["str2dt(NULL)"] = (o == ow_util.str2dt(None))
o = cur.callfunc("pkg_ow_util.f_dt2str", oracledb.DB_TYPE_VARCHAR, [dt.date(1999, 12, 31)])
checks["dt2str(1999-12-31)"] = (o == ow_util.dt2str(dt.date(1999, 12, 31)))
o = cur.callfunc("pkg_ow_util.f_code_desc", oracledb.DB_TYPE_VARCHAR, ["STATUS", None])
try:
    m = ow_util.code_desc(db, "STATUS", None)
except Exception as ex:  # noqa: BLE001
    m = f"raised {type(ex).__name__}: {ex}"
checks["code_desc(STATUS,NULL)"] = (o == m)
checks["code_desc(STATUS,NULL)_values"] = {"oracle": o, "mongo": m}
o = cur.callfunc("pkg_ow_util.f_code_desc", oracledb.DB_TYPE_VARCHAR, ["STATUS", 10])
checks["code_desc(STATUS,10)"] = (o == ow_util.code_desc(db, "STATUS", 10))
probe("P5 PKG_OW_UTIL edge inputs (empty/unicode/300-char md5, NULL dates, NULL code)", all(checks.values()), checks)

reload()
conn.close()
json.dump(out, open("/tmp/w3/probes_b01.json", "w"), indent=1, default=str)
print(json.dumps([(p["probe"], p["result"]) for p in out], indent=1))
sys.exit(0 if all(p["result"] == "PASS" for p in out) else 1)
