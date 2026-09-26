"""Wave-3 independent probes for w3-b02 (u-09 rating, u-10 invoicing, u-11 dunning).
Read-only Oracle refcursor sweeps vs Mongo service code, plus Mongo-side behavioural
probes on the fixture copy (reloaded from Oracle afterwards)."""
import datetime as dt, json, os, sys
from decimal import Decimal
sys.path.insert(0, os.path.expanduser("~/ow-b02/services/legacy-billing/migration/mongo"))
import oracledb, pymongo
import ow_util, rating_service as rs, invoicing_service as inv_s, dunning_service as ds
import fixture_load as fl

db = pymongo.MongoClient(os.environ["MONGO_LOCAL_URI"])["ow_billing_migration"]
conn = fl._oracle_connect("OW_BILLING_FIXTURE_DSN")
cur = conn.cursor()
out = []
def probe(name, ok, detail):
    out.append({"probe": name, "result": "PASS" if ok else "FAIL", "detail": detail})
def reload():
    fl.load_baseline(conn, db)

def norm(v):
    if isinstance(v, dt.datetime): return v.date().isoformat()
    if isinstance(v, dt.date): return v.isoformat()
    if v is None: return None
    if isinstance(v, (int, float, Decimal)) or (isinstance(v, str) and v.replace('.','',1).replace('-','',1).isdigit()):
        try: return str(Decimal(str(v)).quantize(Decimal("0.01")).normalize())
        except Exception: return str(v)
    return v
def refcursor(fn, args):
    rc = cur.callfunc(fn, oracledb.DB_TYPE_CURSOR, args)
    cols = [c[0].lower() for c in rc.description]
    return [dict(zip(cols, r)) for r in rc.fetchall()]
def cmp_rows(o_rows, m_rows):
    if len(o_rows) != len(m_rows): return False, {"oracle_n": len(o_rows), "mongo_n": len(m_rows)}
    for o, m in zip(o_rows, m_rows):
        for k in o:
            if k in m and norm(o[k]) != norm(m[k]):
                return False, {"field": k, "oracle": str(o[k]), "mongo": str(m[k])}
    return True, None

reload()
# P1 read-only sweep: every tenant with usage x 4 monthly periods -> fn_usage_rating / fn_usage_summary / fn_invoice_preview
periods = [(dt.date(2025, 11, 1), dt.date(2025, 11, 30)), (dt.date(2025, 12, 1), dt.date(2025, 12, 31)),
           (dt.date(2026, 1, 1), dt.date(2026, 1, 31)), (dt.date(2026, 2, 1), dt.date(2026, 2, 28))]
tenants = sorted(db["usageEvents"].distinct("tenantId")) + ["no-such-tenant"]
n = 0; mism = []
for t in tenants:
    for ps_, pe in periods:
        for fn, mfn in (("pkg_rating.fn_usage_rating", rs.usage_rating), ("pkg_rating.fn_usage_summary", rs.usage_summary),
                        ("pkg_invoicing.fn_invoice_preview", inv_s.invoice_preview)):
            try:
                o = refcursor(fn, [t, ps_, pe]); m = mfn(db, t, ps_, pe); ok, d = cmp_rows(o, m)
            except Exception as ex:  # noqa: BLE001
                ok, d = False, {"error": f"{type(ex).__name__}: {ex}"}
            n += 1
            if not ok: mism.append({"fn": fn, "tenant": t, "period": ps_.isoformat(), "diff": d})
probe("P1 read-only sweep fn_usage_rating/fn_usage_summary/fn_invoice_preview: 71 tenants x 4 periods vs Mongo", not mism,
      {"comparisons": n, "mismatches": mism[:10], "mismatch_count": len(mism)})

# P1b fn_invoice_lines + fn_overdue_accounts sweep
mism = []
for i in db["invoices"].find({}, {"_id": 1}):
    ok, d = cmp_rows(refcursor("pkg_invoicing.fn_invoice_lines", [i["_id"]]), inv_s.invoice_lines(db, i["_id"]))
    if not ok: mism.append({"invoice": i["_id"], "diff": d})
for d_ in (dt.date(2026, 2, 1), dt.date(2026, 2, 2), dt.date(2026, 2, 14), dt.date(2026, 3, 1), dt.date(2027, 1, 1)):
    ok, d = cmp_rows(refcursor("pkg_dunning.fn_overdue_accounts", [d_]), ds.overdue_accounts(db, d_))
    if not ok: mism.append({"as_of": d_.isoformat(), "diff": d})
probe("P1b fn_invoice_lines (all invoices) + fn_overdue_accounts (5 as_of incl. issue-day boundary) vs Mongo", not mism, {"mismatches": mism})

# P2 JOB_NIGHTLY_DUNNING double call: schedule appends attempt_no+1 (Oracle semantics), suspension + notification idempotent
reload()
as_of = dt.date(2026, 3, 2)  # Monday
base_att = db["dunningAttempts"].count_documents({})
r1 = ds.run_nightly_dunning(db, as_of)
a1 = db["dunningAttempts"].count_documents({}); n1 = db["notifications"].count_documents({"kindCd": 3})
h1 = db["subscriptionsHist"].count_documents({}); t1 = db["tenants"].count_documents({"statusCd": 20})
r2 = ds.run_nightly_dunning(db, as_of)
a2 = db["dunningAttempts"].count_documents({}); n2 = db["notifications"].count_documents({"kindCd": 3})
h2 = db["subscriptionsHist"].count_documents({}); t2 = db["tenants"].count_documents({"statusCd": 20})
overdue = db["invoices"].count_documents({"statusCd": 40})
ok = (r1["scheduled"] == overdue and r2["scheduled"] == overdue and a2 == a1 + overdue and a1 == base_att + overdue
      and len(r1["suspended"]) >= 1 and r2["suspended"] == [] and n1 == n2 and h1 == h2 and t1 == t2
      and db["notifications"].count_documents({"kindCd": 3, "sentAt": ds._utc(as_of)}) == len(r1["suspended"]))
probe("P2 run_nightly_dunning twice same as_of: attempts append (MAX+1, as Oracle), suspension/notification/hist idempotent", ok,
      {"run1": r1, "run2": r2, "attempts": [base_att, a1, a2], "notif_kind3": [n1, n2], "hist": [h1, h2], "suspended_tenants": [t1, t2]})

# P3 sp_suspend_overdue cutoff is day-granular in Oracle (TO_CHAR YYYYMMDD <=): invoice issued 10:00 on cutoff day must still suspend
reload()
inv = db["invoices"].find_one({"statusCd": 40})
db["invoices"].update_one({"_id": inv["_id"]}, {"$set": {"issuedAt": dt.datetime(2026, 2, 13, 10, 0, 0)}})
db["tenants"].update_one({"_id": inv["tenantId"]}, {"$set": {"statusCd": 10}})
sus_midnight_cut = ds.suspend_overdue(db, dt.date(2026, 2, 27))  # cutoff = 2026-02-13 -> Oracle includes (day compare)
reload()
ok = inv["tenantId"] in sus_midnight_cut
probe("P3 suspend_overdue cutoff day-granularity: invoice issued 10:00 on cutoff day (Oracle TO_CHAR<= includes it)", ok,
      {"tenant": inv["tenantId"], "suspended_as_of_2026-02-27_cutoff_2026-02-13": sus_midnight_cut})

# P4 schedule_dunning weekend push-out and TRUNC
reload()
res = {}
for d_ in (dt.date(2026, 2, 27), dt.date(2026, 2, 28), dt.date(2026, 3, 1)):  # Fri, Sat, Sun
    reload(); ds.schedule_dunning(db, d_)
    res[d_.isoformat()] = sorted({a["scheduledFor"].date().isoformat() for a in db["dunningAttempts"].find({"scheduledFor": {"$gte": ds._utc(d_)}})})
ok = res["2026-02-27"] == ["2026-02-27"] and res["2026-02-28"] == ["2026-03-02"] and res["2026-03-01"] == ["2026-03-02"]
probe("P4 schedule_dunning weekend push-out (SAT+2, SUN+1, weekday unchanged)", ok, res)

# P5 sp_issue_invoice twice for same tenant/period -> second must not duplicate (Oracle PK on deterministic id)
reload()
t = "00000000-0000-0000-0000-000000000001"; ps_, pe = dt.date(2026, 2, 1), dt.date(2026, 2, 28)
before = db["invoices"].count_documents({})
outcome = []
for _ in range(2):
    try: inv_s.issue_invoice(db, t, ps_, pe); outcome.append("ok")
    except Exception as ex: outcome.append(type(ex).__name__)  # noqa: BLE001
after = db["invoices"].count_documents({})
probe("P5 issue_invoice replayed for same tenant/period does not create a second invoice", after == before + 1, {"outcomes": outcome, "invoices": [before, after]})

reload()
conn.close()
json.dump(out, open("/tmp/w3/probes_b02.json", "w"), indent=1, default=str)
print(json.dumps([(p["probe"], p["result"]) for p in out], indent=1))
