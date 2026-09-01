#!/usr/bin/env python
"""Wave3b/U6 independent app-level replay.

Read path: pkg_dunning.fn_overdue_accounts invoked LIVE on the Oracle fixture
(SYS_REFCURSOR, read-only) vs DunningService.overdue_accounts on the live Mongo
target — row-for-row parity across boundary as_of dates.

Write path: DUNNING-002..005 recorded Oracle transcripts replayed against the U6
branch's DunningService on a mongomock snapshot of the LIVE target data (Atlas is
never written). Business fields / probes compared to the recorded ground truth.
"""
import json, os, sys, datetime
from datetime import date, datetime as dt, timezone
from decimal import Decimal
from pathlib import Path
from copy import deepcopy

REPO = Path.home() / "wave_recon" / "wt-u6"
sys.path.insert(0, str(REPO / "scripts"))
import oracledb
from pymongo import MongoClient
import mongomock
from tp_mongo.dunning_service import DunningService

out = {"read_path": [], "write_path": []}
ora = oracledb.connect(user="ow_billing", password="ow_billing", dsn="localhost:52521/FREEPDB1")
live = MongoClient(os.environ["MONGODB_ATLAS_URI"])["ow_tp_mongodb_032752"]

# ---- read path -------------------------------------------------------------
def oracle_overdue(as_of: date):
    cur = ora.cursor()
    rc = cur.callfunc("pkg_dunning.fn_overdue_accounts", oracledb.CURSOR, [as_of])
    rows = []
    for tenant_id, invoice_id, total, days, status in rc:
        rows.append((tenant_id, invoice_id, str(Decimal(str(total))), int(days), status))
    return rows

svc = DunningService(live)

def mongo_overdue(as_of: date):
    return [(r["tenant_id"], r["invoice_id"], str(r["total"]), int(r["days_overdue"]), r["tenant_status"])
            for r in svc.overdue_accounts(as_of)]

issued = [r[0] for r in ora.cursor().execute(
    "select distinct trunc(cast(issued_at as date)) from invoices order by 1")]
cases = set()
for d0 in issued:
    d0 = d0.date() if isinstance(d0, dt) else d0
    for delta in (-1, 0, 1, 13, 14, 15):
        cases.add(d0 + datetime.timedelta(days=delta))
cases |= {date(2026, 2, 28), date(2026, 2, 14), date(2026, 2, 15), date(2026, 2, 16),
          date(2026, 2, 17), date(2020, 1, 1), date(2030, 12, 31),
          date(2026, 3, 7), date(2026, 3, 8)}  # SAT/SUN
mismatch = 0
for as_of in sorted(cases):
    a, b = oracle_overdue(as_of), mongo_overdue(as_of)
    eq = a == b
    mismatch += (not eq)
    out["read_path"].append({"as_of": str(as_of), "oracle_rows": len(a), "equal": eq,
                             **({} if eq else {"oracle": a, "mongo": b})})
out["read_path_summary"] = {"cases": len(cases), "mismatches": mismatch}

# ---- write path (mongomock sandbox seeded from LIVE target) ---------------
class _Session:
    def __init__(self, database): self.database = database; self.snapshot = None
    def __enter__(self): return self
    def __exit__(self, exc_type, _e, _t):
        if exc_type is not None and self.snapshot is not None:
            for n in self.database._db.list_collection_names():
                self.database._db[n].delete_many({})
            for n, docs in self.snapshot.items():
                if docs: self.database._db[n].insert_many(deepcopy(docs))
        return False
    def start_transaction(self):
        self.snapshot = {n: list(self.database._db[n].find())
                        for n in self.database._db.list_collection_names()}
        return self

class _Client:
    def __init__(self, database): self.database = database
    def start_session(self): return _Session(self.database)

class _Coll:
    def __init__(self, coll): self._c = coll
    def __getattr__(self, name):
        attr = getattr(self._c, name)
        if callable(attr):
            def wrap(*a, **k): k.pop("session", None); return attr(*a, **k)
            return wrap
        return attr

class _DB:
    name = "ow_tp_mongodb_032752"
    def __init__(self):
        self._db = mongomock.MongoClient(tz_aware=True)["target"]
        self.client = _Client(self)
    def __getitem__(self, name): return _Coll(self._db[name])

def fresh_sandbox():
    db = _DB()
    for coll in ("invoices", "tenants", "subscriptions", "subscriptions_hist", "notifications"):
        docs = list(live[coll].find())
        if docs: db._db[coll].insert_many(docs)
    return DunningService(db), db

def iso_d(v): return v.strftime("%Y-%m-%d")

results = []
# DUNNING-002: schedule as_of 2026-02-14 (SAT -> 16th)
svc2, db2 = fresh_sandbox()
svc2.schedule_dunning(date(2026, 2, 14))
rows = []
for inv in db2._db["invoices"].find({"dunning_attempts.0": {"$exists": True}}):
    for a in inv["dunning_attempts"]:
        rows.append({"attempt_no": a["attempt_no"], "invoice_id": inv["_id"],
                     "scheduled_for": iso_d(a["scheduled_for"]),
                     "status": {10: "scheduled", 20: "sent"}[a["status_cd"]]})
rows.sort(key=lambda r: (r["invoice_id"], r["attempt_no"]))
exp = json.load(open(REPO / "procs/oracle/transcripts/dunning/DUNNING-002.json"))["probes"]["schedule_rows"]
results.append({"scenario": "DUNNING-002", "equal": rows == sorted(exp, key=lambda r: (r["invoice_id"], r["attempt_no"])), "got": rows, "expected": exp})

# DUNNING-003: schedule as_of 2026-02-17 on top of already-loaded attempt state
svc3, db3 = fresh_sandbox()
svc3.schedule_dunning(date(2026, 2, 17))
rows = []
for inv in db3._db["invoices"].find({"dunning_attempts.0": {"$exists": True}}):
    for a in inv["dunning_attempts"]:
        rows.append({"attempt_no": a["attempt_no"], "invoice_id": inv["_id"],
                     "scheduled_for": iso_d(a["scheduled_for"]),
                     "status": {10: "scheduled", 20: "sent"}[a["status_cd"]]})
rows.sort(key=lambda r: (r["invoice_id"], r["attempt_no"]))
exp = json.load(open(REPO / "procs/oracle/transcripts/dunning/DUNNING-003.json"))["probes"]["schedule_rows"]
results.append({"scenario": "DUNNING-003", "equal": rows == sorted(exp, key=lambda r: (r["invoice_id"], r["attempt_no"])), "got": rows, "expected": exp})

# DUNNING-004/005: suspend_overdue as_of 2026-02-28, incl. idempotent second run
for scen, second_run in (("DUNNING-004", False), ("DUNNING-005", True)):
    svc4, db4 = fresh_sandbox()
    svc4.suspend_overdue(date(2026, 2, 28))
    if second_run:
        r2 = svc4.suspend_overdue(date(2026, 2, 28))
    notifs = [{"id": n["_id"], "kind": {3: "suspension"}.get(n["kind_cd"]),
               "sent_at": n["sent_at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "tenant_id": n["tenant_id"]}
              for n in db4._db["notifications"].find({"kind_cd": 3}).sort("_id", 1)]
    exp = json.load(open(REPO / f"procs/oracle/transcripts/dunning/{scen}.json"))["probes"]["suspension_notifications"]
    entry = {"scenario": scen, "equal": notifs == exp, "got": notifs, "expected": exp}
    if second_run:
        entry["second_run_inserted"] = r2["notifications_inserted"]
        entry["notif_count_after_two_runs"] = db4._db["notifications"].count_documents({"kind_cd": 3})
    else:
        # extra checks: tenant + subscriptions suspended, hist pre-image written
        t5 = db4._db["tenants"].find_one({"_id": "00000000-0000-0000-0000-000000000005"})
        entry["tenant5_status_cd"] = t5["status_cd"]
        subs = list(db4._db["subscriptions"].find({"tenant_id": "00000000-0000-0000-0000-000000000005"}))
        entry["tenant5_subs"] = [{"id": s["_id"], "status_cd": s["status_cd"],
                                  "suspended_on": iso_d(s["suspended_on"]) if s.get("suspended_on") else None} for s in subs]
        base_hist = live["subscriptions_hist"].count_documents({})
        entry["hist_rows_added"] = db4._db["subscriptions_hist"].count_documents({}) - base_hist
        added = list(db4._db["subscriptions_hist"].find().sort([("_id", 1)]))[-max(entry["hist_rows_added"], 0):] if entry["hist_rows_added"] else []
        entry["hist_added_ops"] = [h.get("hist_op") for h in added]
        entry["hist_preimage_status"] = [h.get("status_cd") for h in added]
    results.append(entry)

out["write_path"] = results
out["write_path_summary"] = {"scenarios": len(results), "mismatches": sum(1 for r in results if not r["equal"])}

def default(o):
    if isinstance(o, (dt, date)): return o.isoformat()
    return str(o)
print(json.dumps(out, indent=1, default=default))
