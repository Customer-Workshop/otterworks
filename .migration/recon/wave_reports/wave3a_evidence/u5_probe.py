import os, json, decimal, datetime
import oracledb
from pymongo import MongoClient
from bson.decimal128 import Decimal128

u,p,d = os.environ["OW_BILLING_FIXTURE_DSN"].split("/",2)
ora = oracledb.connect(user=u, password=p, dsn=d)
cur = ora.cursor()
mc = MongoClient(os.environ["MONGODB_ATLAS_URI"])
db = mc["ow_tp_mongodb_032752"]
qdb = mc["ow_tp_mongodb_032752_quarantine"]
out = {}

def q(sql, params=None):
    cur.execute(sql, params or {})
    return cur.fetchall()

# counts twice
for _ in (1,2):
    out.setdefault("src_counts", []).append({t: q(f"select count(*) from {t}")[0][0]
        for t in ("INVOICES","INVOICE_LINES","CREDIT_NOTES","DUNNING_ATTEMPTS")})
out["tgt_counts"] = {c: db[c].count_documents({}) for c in ("invoices","credit_notes")}
out["tgt_lines_total"] = list(db.invoices.aggregate([{"$group":{"_id":None,"n":{"$sum":{"$size":"$lines"}}}}]))

# dup keys
out["dup_src"] = {t: q(f"select id, count(*) from {t} group by id having count(*)>1") for t in ("INVOICES","CREDIT_NOTES")}
out["dup_line_key"] = q("select invoice_id, line_no, count(*) from INVOICE_LINES group by invoice_id, line_no having count(*)>1")
# orphan lines
out["orphan_lines"] = q("select count(*) from INVOICE_LINES l where not exists (select 1 from INVOICES i where i.id=l.invoice_id)")[0][0]

# per-field null/missing
def nulls(coll, fields, table):
    r = {}
    for f_src, f_tgt in fields:
        src_null = q(f"select count(*) from {table} where {f_src} is null or {f_src} = ''" if 'char' not in f_src else "")[0][0] if True else 0
        r[f_tgt] = dict(
            src_null=q(f"select count(*) from {table} where {f_src} is null")[0][0],
            tgt_null=db[coll].count_documents({f_tgt: None, f_tgt: {"$type": "null"}}),
            tgt_missing=db[coll].count_documents({f_tgt: {"$exists": False}}))
    return r
out["nulls_invoices"] = nulls("invoices", [("TENANT_ID","tenant_id"),("PERIOD_ID","period_id"),("ISSUED_AT","issued_at"),("SUBTOTAL","subtotal"),("TAX","tax"),("TOTAL","total"),("STATUS_CD","status_cd")], "INVOICES")
out["nulls_credit_notes"] = nulls("credit_notes", [("TENANT_ID","tenant_id"),("ISSUED_ON","issued_on"),("AMOUNT","amount"),("REMAINING_AMOUNT","remaining_amount")], "CREDIT_NOTES")
# empty-string check at source (empty_string_is_null rule)
out["src_empty_strings"] = {t: q(f"select count(*) from {t} where {c} = ' '") for t,c in ()} or "n/a (Oracle treats '' as NULL)"

# embed array length distribution vs child rows
src_dist = dict(q("select invoice_id, count(*) from INVOICE_LINES group by invoice_id"))
tgt_dist = {x["_id"]: x["n"] for x in db.invoices.aggregate([{"$project":{"n":{"$size":"$lines"}}},{"$group":{"_id":"$_id","n":{"$first":"$n"}}}])}
all_inv = [r[0] for r in q("select id from INVOICES")]
out["embed_dist_match"] = all(tgt_dist.get(i,-1) == src_dist.get(i,0) for i in all_inv)
out["embed_dist"] = {"src": src_dist, "tgt": tgt_dist}
out["empty_lines_arrays"] = db.invoices.count_documents({"lines": []})

# line ordering by line_no
bad_order = [d0["_id"] for d0 in db.invoices.find({}, {"lines.line_no":1}) if [l["line_no"] for l in d0["lines"]] != sorted(l["line_no"] for l in d0["lines"])]
out["lines_out_of_order"] = bad_order

# dunning_attempts must be ABSENT (U6-owned)
out["dunning_field_present"] = db.invoices.count_documents({"dunning_attempts": {"$exists": True}})
out["src_dunning_rows"] = q("select count(*) from DUNNING_ATTEMPTS")[0][0]

# min/max boundary docs
def mm(coll, table):
    smin, smax = q(f"select min(id), max(id) from {table}")[0]
    return dict(src=(smin,smax), tgt_min=db[coll].find_one({"_id": smin}) is not None, tgt_max=db[coll].find_one({"_id": smax}) is not None,
                tgt_minmax=[x["_id"] for x in [db[coll].find({},{"_id":1}).sort("_id",1).limit(1)[0], db[coll].find({},{"_id":1}).sort("_id",-1).limit(1)[0]]])
out["minmax_invoices"] = mm("invoices","INVOICES")
out["minmax_credit_notes"] = mm("credit_notes","CREDIT_NOTES")

# full doc-level compare incl aggregate-only decimal fields, exact
def dec(x):
    if isinstance(x, Decimal128): return x.to_decimal()
    return x
mism = []
cur2 = ora.cursor()
cur2.execute("select id, tenant_id, period_id, issued_at, to_char(subtotal), to_char(tax), to_char(total), status_cd from INVOICES")
for iid, ten, per, iss, sub, tax, tot, st in cur2.fetchall():
    doc = db.invoices.find_one({"_id": iid})
    if doc is None: mism.append((iid,"missing")); continue
    exp = dict(tenant_id=ten, period_id=per,
               issued_at=iss.replace(microsecond=(iss.microsecond//1000)*1000) if iss else None,
               subtotal=decimal.Decimal(sub) if sub else None, tax=decimal.Decimal(tax) if tax else None,
               total=decimal.Decimal(tot) if tot else None, status_cd=st)
    got = dict(tenant_id=doc.get("tenant_id"), period_id=doc.get("period_id"), issued_at=doc.get("issued_at"),
               subtotal=dec(doc.get("subtotal")), tax=dec(doc.get("tax")), total=dec(doc.get("total")), status_cd=doc.get("status_cd"))
    for k in exp:
        ev, gv = exp[k], got[k]
        if isinstance(ev, decimal.Decimal) and isinstance(gv, decimal.Decimal):
            if ev.compare(gv) != 0: mism.append((iid,k,str(ev),str(gv)))
        elif ev != gv: mism.append((iid,k,str(ev),str(gv)))
    # lines
    cur2.execute("select line_no, id, line_type, description, to_char(amount) from INVOICE_LINES where invoice_id=:1 order by line_no", [iid])
    slines = cur2.fetchall()
    tlines = doc.get("lines")
    if len(slines) != len(tlines): mism.append((iid,"lines_len",len(slines),len(tlines))); continue
    for (ln,lid,lt,ds,am), tl in zip(slines, tlines):
        e = dict(line_no=ln, id=lid, line_type=lt, description=ds, amount=decimal.Decimal(am) if am else None)
        g = dict(line_no=tl.get("line_no"), id=tl.get("id"), line_type=tl.get("line_type"), description=tl.get("description"), amount=dec(tl.get("amount")))
        for k in e:
            if isinstance(e[k], decimal.Decimal) and isinstance(g[k], decimal.Decimal):
                if e[k].compare(g[k]) != 0: mism.append((iid,"line",ln,k,str(e[k]),str(g[k])))
            elif e[k] != g[k]: mism.append((iid,"line",ln,k,str(e[k]),str(g[k])))
cur2.execute("select id, tenant_id, issued_on, to_char(amount), to_char(remaining_amount) from CREDIT_NOTES")
for cid, ten, iso, am, rem in cur2.fetchall():
    doc = db.credit_notes.find_one({"_id": cid})
    if doc is None: mism.append((cid,"missing")); continue
    e = dict(tenant_id=ten, issued_on=iso, amount=decimal.Decimal(am) if am else None, remaining_amount=decimal.Decimal(rem) if rem else None)
    g = dict(tenant_id=doc.get("tenant_id"), issued_on=doc.get("issued_on"), amount=dec(doc.get("amount")), remaining_amount=dec(doc.get("remaining_amount")))
    for k in e:
        if isinstance(e[k], decimal.Decimal) and isinstance(g[k], decimal.Decimal):
            if e[k].compare(g[k]) != 0: mism.append((cid,k,str(e[k]),str(g[k])))
        elif e[k] != g[k]: mism.append((cid,k,str(e[k]),str(g[k])))
out["doclevel_mismatches"] = mism

# aggregate sums exact
out["src_sums"] = q("select to_char(sum(subtotal)), to_char(sum(tax)), to_char(sum(total)) from INVOICES") + q("select to_char(sum(amount)), to_char(sum(remaining_amount)) from CREDIT_NOTES")
out["tgt_sums"] = [
  [str(x) for x in list(db.invoices.aggregate([{"$group":{"_id":None,"s":{"$sum":"$subtotal"},"t":{"$sum":"$tax"},"tt":{"$sum":"$total"}}}]))],
  [str(x) for x in list(db.credit_notes.aggregate([{"$group":{"_id":None,"a":{"$sum":"$amount"},"r":{"$sum":"$remaining_amount"}}}]))]]

# schema shape: field universe + ns tag
def universe(coll):
    fields = set()
    for doc in db[coll].find({}):
        fields |= set(doc.keys())
    return sorted(fields)
out["fields_invoices"] = universe("invoices")
out["fields_credit_notes"] = universe("credit_notes")
out["ns_ok"] = {c: db[c].count_documents({"ns":"mongo_032752"}) for c in ("invoices","credit_notes")}
out["db_collections"] = sorted(db.list_collection_names())
out["quarantine_collections"] = {c: qdb[c].count_documents({}) for c in qdb.list_collection_names()}

# indexes
out["indexes"] = {c: {k: v["key"] for k,v in db[c].index_information().items()} for c in ("invoices","credit_notes")}

# cross-unit joins
ten_ids = set(x["_id"] for x in db.tenants.find({},{"_id":1}))
per_ids = set(x["_id"] for x in db.rating_periods.find({},{"_id":1}))
out["join_tgt"] = dict(
    inv_tenant_orphans=[x["_id"] for x in db.invoices.find({"tenant_id": {"$nin": list(ten_ids)}})],
    inv_period_orphans=[x["_id"] for x in db.invoices.find({"period_id": {"$nin": list(per_ids)}})],
    cn_tenant_orphans=[x["_id"] for x in db.credit_notes.find({"tenant_id": {"$nin": list(ten_ids)}})])
out["join_src"] = dict(
    inv_tenant=q("select count(*) from INVOICES i where tenant_id is not null and not exists (select 1 from TENANTS t where t.id=i.tenant_id)")[0][0],
    inv_period=q("select count(*) from INVOICES i where period_id is not null and not exists (select 1 from RATING_PERIODS r where r.id=i.period_id)")[0][0],
    cn_tenant=q("select count(*) from CREDIT_NOTES c where tenant_id is not null and not exists (select 1 from TENANTS t where t.id=c.tenant_id)")[0][0])
# status codes decodable
out["inv_status_src"] = sorted(set(r[0] for r in q("select distinct status_cd from INVOICES")))
out["inv_status_tgt"] = sorted(db.invoices.distinct("status_cd"))
out["codes_inv_status"] = sorted(x.get("code") for x in db.codes.find({"domain":{"$regex":"INV", "$options":"i"}},{"code":1})) if "codes" in out["db_collections"] else None

def default(o):
    if isinstance(o,(datetime.datetime, datetime.date)): return o.isoformat()
    if isinstance(o, decimal.Decimal): return str(o)
    if isinstance(o, Decimal128): return str(o)
    return str(o)
print(json.dumps(out, indent=1, default=default))
