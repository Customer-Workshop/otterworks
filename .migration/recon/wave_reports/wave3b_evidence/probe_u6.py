#!/usr/bin/env python
"""Independent adversarial probes for wave3b / U6 (dunning): notifications collection
and dunning_attempts[] embed on invoices. My own code, not the harness."""
import json, os, sys, datetime
import oracledb
from pymongo import MongoClient
from bson.decimal128 import Decimal128

out = {}
ora = oracledb.connect(user="ow_billing", password="ow_billing", dsn="localhost:52521/FREEPDB1")
cur = ora.cursor()
mc = MongoClient(os.environ["MONGODB_ATLAS_URI"])
db = mc["ow_tp_mongodb_032752"]
qdb = mc["ow_tp_mongodb_032752_quarantine"]

def q(sql, binds=()):
    cur.execute(sql, binds); return cur.fetchall()

# 1. counts read twice (drift check)
counts = {}
for t in ("NOTIFICATIONS", "DUNNING_ATTEMPTS", "INVOICES", "INVOICE_LINES"):
    a = q(f"select count(*) from {t}")[0][0]
    b = q(f"select count(*) from {t}")[0][0]
    counts[t] = (a, b, a == b)
out["source_counts_twice"] = counts
out["tgt_counts"] = {
    "notifications": db.notifications.count_documents({}),
    "invoices": db.invoices.count_documents({}),
    "sum_dunning_embed": list(db.invoices.aggregate([{"$group": {"_id": None, "n": {"$sum": {"$size": {"$ifNull": ["$dunning_attempts", []]}}}}}]))[0]["n"],
}

# 2. duplicate keys
out["dup_src_notif_id"] = q("select count(*) from (select id from notifications group by id having count(*)>1)")[0][0]
out["dup_src_dun_key"] = q("select count(*) from (select invoice_id, attempt_no from dunning_attempts group by invoice_id, attempt_no having count(*)>1)")[0][0]
dup_tgt = list(db.notifications.aggregate([{"$group": {"_id": "$_id", "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}}]))
out["dup_tgt_notif"] = len(dup_tgt)

# 3. orphan dunning_attempts (child without invoice)
out["src_orphan_dunning"] = q("select count(*) from dunning_attempts d where not exists (select 1 from invoices i where i.id=d.invoice_id)")[0][0]

# 4. embed length distribution vs child rows per invoice
src_dist = dict(q("select i.id, (select count(*) from dunning_attempts d where d.invoice_id=i.id) from invoices i"))
tgt_dist = {d["_id"]: (len(d["dunning_attempts"]) if "dunning_attempts" in d else None)
            for d in db.invoices.find({}, {"dunning_attempts": 1})}
out["embed_dist_src"] = src_dist
out["embed_dist_tgt"] = {k: v for k, v in tgt_dist.items()}
out["embed_dist_match"] = all((tgt_dist.get(k) or 0) == v for k, v in src_dist.items()) and set(src_dist) == set(tgt_dist)
out["invoices_missing_dunning_field"] = [k for k, v in tgt_dist.items() if v is None]
out["invoices_empty_dunning_array"] = [k for k, v in tgt_dist.items() if v == 0]

# 5. null/missing distributions per mapped field
nulls = {}
for t, cols in (("NOTIFICATIONS", ["TENANT_ID", "KIND_CD", "SENT_AT"]),
                ("DUNNING_ATTEMPTS", ["ID", "TENANT_ID", "SCHEDULED_FOR", "STATUS_CD"])):
    for col in cols:
        nulls[f"src.{t}.{col}"] = q(f"select count(*) from {t} where {col} is null")[0][0]
for f in ("tenant_id", "kind_cd", "sent_at"):
    nulls[f"tgt.notifications.{f}.null"] = db.notifications.count_documents({f: None})
    nulls[f"tgt.notifications.{f}.missing"] = db.notifications.count_documents({f: {"$exists": False}})
out["null_missing"] = nulls

# 6. full doc-level compare, my own canonicalization
def dec(x):
    return str(x)
src_notif = q("select id, tenant_id, kind_cd, to_char(sent_at,'YYYY-MM-DD\"T\"HH24:MI:SS.FF3') from notifications order by id")
tgt_notif = list(db.notifications.find({}).sort("_id", 1))
mism = []
for s, t in zip(src_notif, tgt_notif):
    tt = (t["_id"], t["tenant_id"], t["kind_cd"], t["sent_at"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3])
    if (s[0], s[1], s[2], s[3]) != tt:
        mism.append({"src": s, "tgt": [str(x) for x in tt]})
out["notif_doc_compare_mismatches"] = mism
out["notif_doc_compare_n"] = len(src_notif)

src_dun = q("select invoice_id, attempt_no, id, tenant_id, to_char(scheduled_for,'YYYY-MM-DD\"T\"HH24:MI:SS'), status_cd from dunning_attempts order by invoice_id, attempt_no")
dun_mism = []
for inv_id, att_no, did, ten, sched, st in src_dun:
    doc = db.invoices.find_one({"_id": inv_id})
    arr = (doc or {}).get("dunning_attempts", [])
    m = [a for a in arr if a.get("attempt_no") == att_no]
    if len(m) != 1:
        dun_mism.append({"invoice": inv_id, "attempt_no": att_no, "found": len(m)}); continue
    a = m[0]
    tt = (a.get("id"), a.get("tenant_id"), a["scheduled_for"].strftime("%Y-%m-%dT%H:%M:%S"), a.get("status_cd"))
    if (did, ten, sched, st) != tt:
        dun_mism.append({"invoice": inv_id, "attempt_no": att_no, "src": [did, ten, sched, str(st)], "tgt": [str(x) for x in tt]})
out["dunning_doc_compare_mismatches"] = dun_mism
out["dunning_doc_compare_n"] = len(src_dun)

# ordering within array by attempt_no
bad_order = []
for d in db.invoices.find({"dunning_attempts.0": {"$exists": True}}, {"dunning_attempts.attempt_no": 1}):
    seq = [a["attempt_no"] for a in d["dunning_attempts"]]
    if seq != sorted(seq):
        bad_order.append(d["_id"])
out["dunning_array_order_violations"] = bad_order

# 7. min/max boundary docs
out["src_notif_minmax"] = q("select min(id), max(id) from notifications")[0]
tn = sorted(d["_id"] for d in db.notifications.find({}, {"_id": 1}))
out["tgt_notif_minmax"] = (tn[0], tn[-1]) if tn else (None, None)

# 8. schema shape / field universes / ns marker
univ = set()
for d in db.notifications.find({}):
    univ |= set(d.keys())
out["notif_field_universe"] = sorted(univ)
out["notif_ns_ok"] = db.notifications.count_documents({"ns": "mongo_032752"}) == db.notifications.count_documents({})
dun_univ = set()
for d in db.invoices.find({"dunning_attempts.0": {"$exists": True}}, {"dunning_attempts": 1}):
    for a in d["dunning_attempts"]:
        dun_univ |= set(a.keys())
out["dunning_embed_field_universe"] = sorted(dun_univ)

# invoices doc integrity untouched otherwise (U5 fields still intact): aggregate sums
s = q("select to_char(sum(subtotal),'FM9999990.00'), to_char(sum(tax),'FM9999990.00'), to_char(sum(total),'FM9999990.00') from invoices")[0]
agg = list(db.invoices.aggregate([{"$group": {"_id": None, "sub": {"$sum": "$subtotal"}, "tax": {"$sum": "$tax"}, "tot": {"$sum": "$total"}}}]))[0]
out["invoice_sums"] = {"src": s, "tgt": [str(agg["sub"]), str(agg["tax"]), str(agg["tot"])]}

# 9. collection inventory + quarantine
out["target_collections"] = sorted(db.list_collection_names())
out["quarantine_collections"] = {c: qdb[c].count_documents({}) for c in qdb.list_collection_names()}

# 10. cross-unit refs
refs = {}
refs["src_notif_tenant_orphans"] = q("select count(*) from notifications n where not exists (select 1 from tenants t where t.id=n.tenant_id)")[0][0]
tenant_ids = {d["_id"] for d in db.tenants.find({}, {"_id": 1})}
refs["tgt_notif_tenant_orphans"] = db.notifications.count_documents({"tenant_id": {"$nin": list(tenant_ids)}})
refs["src_dun_tenant_orphans"] = q("select count(*) from dunning_attempts d where not exists (select 1 from tenants t where t.id=d.tenant_id)")[0][0]
bad = []
for d in db.invoices.find({"dunning_attempts.0": {"$exists": True}}, {"dunning_attempts.tenant_id": 1}):
    for a in d["dunning_attempts"]:
        if a["tenant_id"] not in tenant_ids:
            bad.append(d["_id"])
refs["tgt_dun_tenant_orphans"] = bad
# dunning tenant matches parent invoice tenant?
refs["src_dun_tenant_vs_invoice"] = q("select count(*) from dunning_attempts d join invoices i on i.id=d.invoice_id where d.tenant_id<>i.tenant_id")[0][0]
# code decodability: notification kind + dunning status
refs["src_notif_kind_distinct"] = [r[0] for r in q("select distinct kind_cd from notifications order by 1")]
refs["tgt_notif_kind_distinct"] = sorted(db.notifications.distinct("kind_cd"))
refs["src_codes_notif_kind"] = [r[0] for r in q("select code_val from codes where code_type like '%NOTIF%' or code_type like '%KIND%' order by 1")]
refs["src_dun_status_distinct"] = [r[0] for r in q("select distinct status_cd from dunning_attempts order by 1")]
refs["tgt_dun_status_distinct"] = sorted({a["status_cd"] for d in db.invoices.find({"dunning_attempts.0": {"$exists": True}}, {"dunning_attempts.status_cd": 1}) for a in d["dunning_attempts"]})
refs["codes_types"] = [r[0] for r in q("select distinct code_type from codes order by 1")]
out["cross_unit"] = refs

# 11. indexes on notifications
out["notif_indexes"] = {k: v["key"] for k, v in db.notifications.index_information().items()}

def default(o):
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    if isinstance(o, Decimal128):
        return str(o)
    return str(o)
print(json.dumps(out, indent=1, default=default))
