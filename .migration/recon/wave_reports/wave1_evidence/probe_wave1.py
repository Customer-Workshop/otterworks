#!/usr/bin/env python3
"""Wave 1 independent adversarial probes (U1 customers/hist, U2 invoice_feed)."""
import json, os, sys
from collections import Counter
from decimal import Decimal
import oracledb, pymongo
from bson.decimal128 import Decimal128

u, p, d = os.environ["OW_BILLING_FIXTURE_DSN"].split("/", 2)
src = oracledb.connect(user=u, password=p, dsn=d)
cur = src.cursor()
m = pymongo.MongoClient(os.environ["MONGODB_ATLAS_URI"])
db = m["ow_tp_mongodb_032752"]
qdb = m["ow_tp_mongodb_032752_quarantine"]
out = {}

def q1(sql):
    cur.execute(sql)
    return cur.fetchone()[0]

# ---- counts / dup keys ----
out["counts"] = {
    "src_customer_master": q1("select count(*) from customer_master"),
    "src_hist": q1("select count(*) from customer_master_hist"),
    "src_inv_hdr": q1("select count(*) from invoice_header"),
    "src_inv_line": q1("select count(*) from invoice_line"),
    "src_inv_line_orphan": q1("select count(*) from invoice_line l where not exists (select 1 from invoice_header h where h.invoice_id=l.invoice_id)"),
    "src_eav_customer": q1("select count(*) from entity_attr_value where entity_type='CUSTOMER'"),
    "tgt_customers": db.customers.count_documents({}),
    "tgt_hist": db.customer_master_hist.count_documents({}),
    "tgt_invoice_feed": db.invoice_feed.count_documents({}),
    "tgt_lines_embedded": next(db.invoice_feed.aggregate([{"$group": {"_id": None, "n": {"$sum": {"$size": {"$ifNull": ["$lines", []]}}}}}]))["n"],
    "tgt_attrs_embedded": next(db.customers.aggregate([{"$group": {"_id": None, "n": {"$sum": {"$size": {"$ifNull": ["$attributes", []]}}}}}]))["n"],
    "quarantine_collections": sorted(qdb.list_collection_names()),
}
for c in qdb.list_collection_names():
    out["counts"]["q_" + c] = qdb[c].count_documents({})

out["dup_keys"] = {
    "src_dup_cust_id": q1("select count(*) from (select cust_id from customer_master group by cust_id having count(*)>1)"),
    "src_dup_hist_id": q1("select count(*) from (select hist_id from customer_master_hist group by hist_id having count(*)>1)"),
    "src_dup_invoice_id": q1("select count(*) from (select invoice_id from invoice_header group by invoice_id having count(*)>1)"),
    "src_dup_line_id": q1("select count(*) from (select line_id from invoice_line group by line_id having count(*)>1)"),
    "tgt_dup_line_id_within_docs": len(list(db.invoice_feed.aggregate([
        {"$unwind": "$lines"}, {"$group": {"_id": "$lines.line_id", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}, {"$limit": 5}]))),
}

# ---- embed-array length distribution vs source child-row distribution ----
def src_dist(sql):
    cur.execute(sql)
    return dict(Counter(int(r[0]) for r in cur.fetchall()))
def tgt_dist(coll, path):
    return {int(r["_id"]): r["n"] for r in db[coll].aggregate(
        [{"$project": {"k": {"$size": {"$ifNull": ["$" + path, []]}}}},
         {"$group": {"_id": "$k", "n": {"$sum": 1}}}])}
s_lines = src_dist("select nvl(c.n,0) from invoice_header h left join (select invoice_id, count(*) n from invoice_line group by invoice_id) c on c.invoice_id=h.invoice_id")
t_lines = tgt_dist("invoice_feed", "lines")
s_attr = src_dist("select nvl(c.n,0) from customer_master cm left join (select entity_id, count(*) n from entity_attr_value where entity_type='CUSTOMER' group by entity_id) c on c.entity_id=cm.cust_id")
t_attr = tgt_dist("customers", "attributes")
out["embed_dist"] = {"lines_src": s_lines, "lines_tgt": t_lines, "lines_equal": s_lines == t_lines,
                     "attrs_src": s_attr, "attrs_tgt": t_attr, "attrs_equal": s_attr == t_attr}

# ---- null/missing distribution per field (targeted incl. v1.1 amended fields) ----
U1_FIELDS = ["sub_status_cd", "territory_cd", "channel_cd", "rate_class_cd", "phone3_type_cd",
             "phone4_type_cd", "credit_limit_amt", "ltd_billed_amt", "ytd_paid_amt",
             "udf_amt_01", "udf_amt_10", "cur_bal_amt", "signup_dt", "related_acct_ids",
             "tenant_id", "cust_name", "tax_exempt_yn"]
nm = {}
for f in U1_FIELDS:
    src_null = q1(f"select count(*) from customer_master where {f} is null")
    t_null = db.customers.count_documents({f: None, f: {"$type": "null"}})
    t_missing = db.customers.count_documents({f: {"$exists": False}})
    nm[f] = {"src_null": src_null, "tgt_null": t_null, "tgt_missing": t_missing,
             "ok": src_null == t_null and t_missing == 0}
out["null_missing_customers"] = nm
nm2 = {}
for f in ["cust_id", "tenant_id", "invoice_dt", "due_dt", "total_amt", "batch_no", "status_cd", "invoice_no"]:
    src_null = q1(f"select count(*) from invoice_header where {f} is null")
    t_null = db.invoice_feed.count_documents({f: {"$type": "null"}})
    t_missing = db.invoice_feed.count_documents({f: {"$exists": False}})
    nm2[f] = {"src_null": src_null, "tgt_null": t_null, "tgt_missing": t_missing,
              "ok": src_null == t_null and t_missing == 0}
out["null_missing_invoice_feed"] = nm2

# ---- min/max boundary docs, doc-level ----
def fetch_row(sql):
    cur.execute(sql)
    cols = [c[0].lower() for c in cur.description]
    r = cur.fetchone()
    return dict(zip(cols, r))
def canon(v):
    if isinstance(v, Decimal128): v = v.to_decimal()
    if isinstance(v, Decimal): v = str(v.normalize())
    if isinstance(v, float): v = str(Decimal(str(v)).normalize())
    if isinstance(v, int): v = str(Decimal(v).normalize())
    if isinstance(v, str) and v == "": v = None
    return v
def cmp_doc(row, doc, keymap):
    diffs = []
    for s, t in keymap:
        a, b = canon(row.get(s)), canon(doc.get(t))
        if isinstance(a, str) and a.rstrip() != a and (b is None or b == a.rstrip()):
            a = a.rstrip() or None
        if a != b:
            diffs.append((s, repr(a), repr(b)))
    return diffs

u1map = json.load(open(os.path.expanduser("~/wave_recon/u1/.migration/recon/U1/mapping/u1.json")))
cust_fields = [(f["source"].lower(), f["target"]) for f in u1map["collections"][0]["fields"]]
bnd = {}
for lbl, sql in [("min", "select * from customer_master where cust_id=(select min(cust_id) from customer_master)"),
                 ("max", "select * from customer_master where cust_id=(select max(cust_id) from customer_master)")]:
    row = fetch_row(sql)
    doc = db.customers.find_one({"_id": row["cust_id"]})
    bnd["cust_" + lbl] = {"key": row["cust_id"], "found": doc is not None,
                          "diffs": cmp_doc(row, doc, cust_fields) if doc else "MISSING"}
u2map = json.load(open(os.path.expanduser("~/wave_recon/u2/.migration/recon/U2/mapping/u2.json")))
inv_fields = [(f["source"].lower(), f["target"]) for f in u2map["collections"][0]["fields"]]
line_fields = [(f["source"].lower(), f["target"]) for f in u2map["collections"][0]["embeds"][0]["fields"]]
for lbl, sql in [("min", "select * from invoice_header where invoice_id=(select min(invoice_id) from invoice_header)"),
                 ("max", "select * from invoice_header where invoice_id=(select max(invoice_id) from invoice_header)")]:
    row = fetch_row(sql)
    doc = db.invoice_feed.find_one({"_id": row["invoice_id"]})
    res = {"key": row["invoice_id"], "found": doc is not None,
           "diffs": cmp_doc(row, doc, inv_fields) if doc else "MISSING"}
    if doc:
        cur.execute("select * from invoice_line where invoice_id=:1 order by line_id", [row["invoice_id"]])
        cols = [c[0].lower() for c in cur.description]
        srows = [dict(zip(cols, r)) for r in cur.fetchall()]
        dlines = sorted(doc.get("lines", []), key=lambda x: x["line_id"])
        res["line_count_equal"] = len(srows) == len(dlines)
        ldiffs = []
        for sr, dl in zip(srows, dlines):
            if canon(sr["line_id"]) != canon(dl["line_id"]):
                ldiffs.append(("line_id", sr["line_id"], dl["line_id"]))
            ldiffs += cmp_doc(sr, dl, line_fields)
        res["line_diffs"] = ldiffs
    bnd["inv_" + lbl] = res
out["boundary_docs"] = bnd

# ---- aggregate-only field doc-level spot checks (decimals) ----
spot = {}
cur.execute("select cust_id, cur_bal_amt, past_due_amt, ytd_billed_amt, credit_limit_amt from customer_master order by dbms_random.value fetch first 25 rows only")
bad = []
for cid, a, b_, c_, e_ in cur.fetchall():
    doc = db.customers.find_one({"_id": cid}, {"cur_bal_amt": 1, "past_due_amt": 1, "ytd_billed_amt": 1, "credit_limit_amt": 1})
    for name, v in [("cur_bal_amt", a), ("past_due_amt", b_), ("ytd_billed_amt", c_), ("credit_limit_amt", e_)]:
        if canon(v) != canon(doc.get(name)):
            bad.append((cid, name, str(v), str(doc.get(name))))
spot["customers_decimal_spot_25"] = bad
cur.execute("select h.invoice_id, h.total_amt, (select nvl(sum(l.amount),0) from invoice_line l where l.invoice_id=h.invoice_id) from invoice_header h order by dbms_random.value fetch first 25 rows only")
bad2 = []
for iid, tot, lsum in cur.fetchall():
    doc = db.invoice_feed.find_one({"_id": iid})
    if canon(tot) != canon(doc.get("total_amt")):
        bad2.append((iid, "total_amt", str(tot), str(doc.get("total_amt"))))
    dsum = sum((x["amount"].to_decimal() if isinstance(x.get("amount"), Decimal128) else Decimal(str(x.get("amount") or 0))) for x in doc.get("lines", []))
    if Decimal(lsum or 0) != dsum:
        bad2.append((iid, "sum(lines.amount)", str(lsum), str(dsum)))
spot["invoice_feed_decimal_spot_25"] = bad2
out["aggregate_spot"] = spot

# ---- schema shape / ns stamp / stray collections ----
expect_cust = {t for _, t in cust_fields} | {"_id", "attributes", "ns"}
stray = list(db.customers.aggregate([
    {"$project": {"kv": {"$objectToArray": "$$ROOT"}}}, {"$unwind": "$kv"},
    {"$group": {"_id": "$kv.k"}}]))
out["schema"] = {
    "customers_field_universe_minus_expected": sorted({x["_id"] for x in stray} - expect_cust),
    "customers_ns_ok": db.customers.count_documents({"ns": {"$ne": "mongo_032752"}}) == 0,
    "hist_ns_ok": db.customer_master_hist.count_documents({"ns": {"$ne": "mongo_032752"}}) == 0,
    "invoice_feed_ns_ok": db.invoice_feed.count_documents({"ns": {"$ne": "mongo_032752"}}) == 0,
    "target_db_collections": sorted(db.list_collection_names()),
}
json.dump(out, open("/tmp/wave1_recheck/probe_wave1.out.json", "w"), indent=2, default=str)
print(json.dumps(out, indent=2, default=str)[:6000])
