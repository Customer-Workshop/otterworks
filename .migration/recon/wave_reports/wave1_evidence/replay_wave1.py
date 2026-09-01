#!/usr/bin/env python3
"""Wave 1 app-level replay: RPT-114 balances (U1) + status/line rollups (U2) on both stacks."""
import hashlib, json, os, sys
from decimal import Decimal, ROUND_HALF_UP
import oracledb, pymongo

sys.path.insert(0, os.path.expanduser("~/wave_recon/u2/services/legacy-billing/app"))
import importlib.util
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
r2 = load("reports_u2", os.path.expanduser("~/wave_recon/u2/services/legacy-billing/app/reports.py"))
r1 = load("reports_u1", os.path.expanduser("~/wave_recon/u1/services/legacy-billing/app/reports.py"))

u, p, d = os.environ["OW_BILLING_FIXTURE_DSN"].split("/", 2)
ora = oracledb.connect(user=u, password=p, dsn=d)
cur = ora.cursor()
mc = pymongo.MongoClient(os.environ["MONGODB_ATLAS_URI"])
db = mc["ow_tp_mongodb_032752"]

NS = "mongo_032752"
batch = int(os.environ.get("BATCH_OVERRIDE") or r2.ns_batch_no(NS))
out = {"ns": NS, "batch_no": batch}

def osql(sql):
    cur.execute(sql, {"batch_no": batch})
    return cur.fetchall()

# ---- U2 status rollup ----
o_status = [tuple(r) for r in osql(r2.STATUS_SQL if hasattr(r2, "STATUS_SQL") else None)] if hasattr(r2, "STATUS_SQL") else None
STATUS_SQL = """
SELECT NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')') AS status_desc,
       COUNT(*) AS invoice_count,
       TO_CHAR(SUM(h.total_amt), 'FM999999999999990.00') AS header_total_amt
  FROM invoice_header h, codes st
 WHERE h.batch_no = :batch_no
   AND st.code_type (+) = 'INV_STATUS' AND st.code_val (+) = h.status_cd
 GROUP BY NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')') ORDER BY 1"""
LINE_SQL = """
SELECT NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')') AS status_desc,
       DECODE(l.line_type_cd, 1,'CHARGE',2,'CREDIT',3,'ADJUSTMENT',9,'MISC',
              'UNKNOWN(' || TO_CHAR(l.line_type_cd) || ')') AS line_type,
       COUNT(*) AS line_count,
       TO_CHAR(SUM(l.amount),  'FM999999999999990.00') AS line_amount,
       TO_CHAR(SUM(l.tax_amt), 'FM999999999999990.00') AS line_tax,
       COUNT(DISTINCT h.invoice_id) AS invoices_touched
  FROM invoice_header h, invoice_line l, codes st
 WHERE h.batch_no = :batch_no AND h.invoice_id = l.invoice_id
   AND st.code_type (+) = 'INV_STATUS' AND st.code_val (+) = h.status_cd
 GROUP BY NVL(st.code_desc, 'UNKNOWN(' || TO_CHAR(h.status_cd) || ')'),
          DECODE(l.line_type_cd, 1,'CHARGE',2,'CREDIT',3,'ADJUSTMENT',9,'MISC',
                 'UNKNOWN(' || TO_CHAR(l.line_type_cd) || ')')
 ORDER BY 1, 2"""
BALANCES_SQL = r2.BALANCES_SQL

o_status = [tuple(r) for r in osql(STATUS_SQL)]
m_status = [
    (doc["_id"], int(doc["invoice_count"]), r2.amount_str(doc["header_total_amt"]))
    for doc in db.invoice_feed.aggregate(r2.status_pipeline(batch))
]
out["status_rollup"] = {"oracle": o_status, "mongo": m_status, "equal": o_status == m_status}

o_line = [tuple(r) for r in osql(LINE_SQL)]
m_line = [
    (doc["_id"]["status_desc"], doc["_id"]["line_type"], int(doc["line_count"]),
     r2.amount_str(doc["line_amount"]), r2.amount_str(doc["line_tax"]), int(doc["invoices_touched"]))
    for doc in db.invoice_feed.aggregate(r2.line_pipeline(batch))
]
out["line_rollup"] = {"oracle_rows": len(o_line), "mongo_rows": len(m_line),
                      "equal": o_line == m_line,
                      "diff": [x for x in zip(o_line, m_line) if x[0] != x[1]][:5]}

# ---- U1 balances ----
o_bal = tuple(osql(BALANCES_SQL)[0])
docs = list(db.customers.aggregate(r1.balances_pipeline(batch)))
if docs:
    doc = docs[0]
    m_bal = (int(doc["customer_count"]),
             r1.fm_amount(doc["current_balance_total"].to_decimal() if hasattr(doc["current_balance_total"], "to_decimal") else doc["current_balance_total"]),
             r1.fm_amount(doc["past_due_total"].to_decimal() if hasattr(doc["past_due_total"], "to_decimal") else doc["past_due_total"]))
else:
    m_bal = (0, None, None)
out["balances"] = {"oracle": o_bal, "mongo": m_bal, "equal": o_bal == m_bal}

# ---- point lookups: 20 random customers by cust_no+tenant (app-style search) ----
cur.execute("select cust_id, cust_no, tenant_id, cust_name_upper from customer_master order by dbms_random.value fetch first 20 rows only")
fails = []
for cid, cno, tid, cnu in cur.fetchall():
    doc = db.customers.find_one({"cust_no": cno, "tenant_id": tid})
    if not doc or doc["_id"] != cid or doc.get("cust_name_upper") != cnu:
        fails.append(cno)
out["customer_point_lookup_20"] = {"failures": fails}

json.dump(out, open("/tmp/wave1_recheck/replay_wave1.out.json", "w"), indent=2, default=str)
print(json.dumps({k: (v if k in ("ns", "batch_no") else {kk: vv for kk, vv in v.items() if kk != "oracle" and kk != "mongo" or k == "balances"}) for k, v in out.items()}, indent=2, default=str))
