"""Wave 3a app-level replay: PKG_INVOICING read paths (legacy SQL replicated
read-only, verbatim from the package body -- the package is never invoked
because compute_preview -> pkg_rating logs via autonomous txn) vs the U5
branch's InvoicingService against Mongo. Plus recorded Oracle transcript
replay for fn_invoice_preview scenarios (ground truth from the real package).
"""
import json, os, sys, glob
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import oracledb
from pymongo import MongoClient
from bson.decimal128 import Decimal128

sys.path.insert(0, os.path.expanduser("~/wave_recon/wt-u5/scripts"))
from tp_mongo import rating_service, invoicing_service

oracledb.defaults.fetch_decimals = True
USER, PWD, DSN = os.environ["OW_BILLING_FIXTURE_DSN"].split("/", 2)
ora = oracledb.connect(user=USER, password=PWD, dsn=DSN)
cur = ora.cursor()
db = MongoClient(os.environ["MONGODB_ATLAS_URI"])["ow_tp_mongodb_032752"]
svc = invoicing_service.InvoicingService(db, rating_service.RatingService(db))
out = {"failures": []}

def norm(v):
    if isinstance(v, Decimal128): v = v.to_decimal()
    if isinstance(v, int): v = Decimal(v)
    if isinstance(v, Decimal):
        if v == 0: return "0"
        return format(v.normalize(), "f")
    return v

# ---- read-only replica of pkg_rating.compute_rating (validated in wave 2, 31/31) ----
def ora_overage(t, ps, pe):
    psd, ped = datetime.combine(ps, datetime.min.time()), datetime.combine(pe, datetime.min.time())
    cur.execute("""
      SELECT id, status_cd, suspended_on, plan_id FROM (
        SELECT s.id, s.status_cd, s.suspended_on, s.plan_id FROM subscriptions s
         WHERE s.tenant_id=:t AND s.starts_on<=:pe
           AND (s.ends_on IS NULL OR s.ends_on>=:ps)
         ORDER BY s.starts_on DESC) WHERE ROWNUM<=1""", t=t, ps=psd, pe=ped)
    sub = cur.fetchone()
    included = rate = None
    v_sub_status = v_susp = None
    if sub:
        v_sub_status, v_susp = sub[1], sub[2]
        cur.execute("select included_units, overage_rate from plans where id=:i", i=sub[3])
        p = cur.fetchone()
        if p: included, rate = p
    cur.execute("""
      SELECT NVL(SUM(NVL(units,0)),0) FROM usage_events u WHERE u.tenant_id=:t
        AND TO_CHAR(u.occurred_at,'YYYYMMDD') >= TO_CHAR(:ps,'YYYYMMDD')
        AND TO_CHAR(u.occurred_at,'YYYYMMDD') <= TO_CHAR(:pe,'YYYYMMDD')""",
        t=t, ps=psd, pe=ped)
    used = cur.fetchone()[0]
    cur.execute("""
      SELECT NVL(SUM(NVL(rr.rollover_units,0)),0) FROM rating_results rr, rating_periods rp
       WHERE rp.id=rr.period_id AND rp.tenant_id=:t AND rp.period_start<:ps
         AND rp.period_start>=ADD_MONTHS(:ps,-3)""", t=t, ps=psd)
    prior = cur.fetchone()[0]
    rollover = min(prior, included * 2) if included is not None else prior
    billable = max(used - rollover - included, 0) if included is not None else 0
    first = min(billable, 101); second = max(billable - 101, 0)
    overage = None if rate is None else (Decimal(first) * rate +
              Decimal(second) * rate * Decimal("1.5")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if v_sub_status == 20 and v_susp is not None and psd <= v_susp <= ped:
        factor = Decimal((ped - v_susp).days + 1) / Decimal((ped - psd).days + 1)
        overage = None if overage is None else (overage * factor).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return overage

# ---- read-only replica of pkg_invoicing.compute_preview + fn_invoice_preview ----
def ora_preview(t, ps, pe):
    psd, ped = datetime.combine(ps, datetime.min.time()), datetime.combine(pe, datetime.min.time())
    cur.execute("""
      SELECT code, monthly_fee FROM (SELECT p.code, p.monthly_fee
          FROM subscriptions s, plans p
         WHERE p.id = s.plan_id AND s.tenant_id = :t
           AND s.starts_on <= :pe AND (s.ends_on IS NULL OR s.ends_on >= :ps)
         ORDER BY s.starts_on DESC) WHERE ROWNUM <= 1""", t=t, ps=psd, pe=ped)
    row = cur.fetchone()
    plan_code, plan_fee = (row if row else (None, None))
    overage = ora_overage(t, ps, pe)
    credit = Decimal(0)
    cur.execute("SELECT remaining_amount FROM credit_notes WHERE tenant_id = :t AND remaining_amount > 0", t=t)
    for (r,) in cur.fetchall():
        credit += (r if r is not None else Decimal(0))
    cur.execute("SELECT NVL(tax_exempt_yn,'N') FROM tenants WHERE id = :t", t=t)
    row = cur.fetchone()
    exempt = row[0] if row else 'N'
    # let Oracle do every arithmetic step, verbatim expressions
    cur.execute("""
      SELECT DECODE(:ex, 'Y', 0, (:fee + :ov) * 0.0825),
             ROUND(:fee, 2), ROUND(:ov, 2),
             DECODE(:ex, 'Y', 0, (:fee + :ov) * 0.0825) / 2,
             ROUND(:fee + :ov + DECODE(:ex, 'Y', 0, (:fee + :ov) * 0.0825), 2),
             LEAST(:cr, NVL(ROUND(:fee + :ov + DECODE(:ex, 'Y', 0, (:fee + :ov) * 0.0825), 2), :cr))
        FROM dual""", ex=exempt, fee=plan_fee, ov=overage, cr=credit)
    tax, fee_r, ov_r, tax_half, cap, credit_app = cur.fetchone()
    return [
        (1, 'plan', plan_code, fee_r, Decimal(0), Decimal(0), fee_r),
        (2, 'usage', 'usage overage', ov_r, Decimal(0), Decimal(0), ov_r),
        (3, 'tax', 'regional tax', tax_half, Decimal(0), Decimal(0), tax_half),
        (4, 'tax', 'local tax', tax_half, Decimal(0), Decimal(0), tax_half),
        (5, 'credit', 'credit notes', Decimal(0), Decimal(0), credit_app, -credit_app),
    ]

def mongo_preview(t, ps, pe):
    rows = svc.invoice_preview(t, ps, pe)
    return [(r["line_no"], r["line_type"], r["description"], r["amount"],
             r["tax_amount"], r["credit_applied"], r["total"]) for r in rows]

def cmp_rows(a, b):
    return [[None if x is None else norm(x) for x in r] for r in a] == \
           [[None if x is None else norm(x) for x in r] for r in b]

# ---- cases ----
cur.execute("select id from tenants")
tenants = [r[0] for r in cur.fetchall()]
cur.execute("select tenant_id, period_start, period_end from rating_periods")
periods = [(r[0], r[1].date(), r[2].date()) for r in cur.fetchall()]
cases = periods[:]
for t in tenants:
    cases.append((t, date(2026, 2, 1), date(2026, 2, 28)))
    cases.append((t, date(2025, 4, 1), date(2025, 4, 30)))
cases += [("no-such-tenant", date(2026, 2, 1), date(2026, 2, 28))]
cur.execute("select tenant_id, suspended_on from subscriptions where suspended_on is not null")
for st, so in cur.fetchall():
    sod = so.date()
    cases += [(st, sod.replace(day=1), (sod.replace(day=1) + timedelta(days=40)).replace(day=1) - timedelta(days=1)),
              (st, sod - timedelta(days=10), sod + timedelta(days=10))]
# transcript scenarios
tx_cases = []
for f in sorted(glob.glob(os.path.expanduser("~/wave_recon/wt-u5/procs/oracle/transcripts/invoicing/*.json"))):
    tx = json.load(open(f))
    if tx["entrypoint"].endswith("fn_invoice_preview"):
        i = tx["inputs"]
        tx_cases.append((tx["scenario"], i["tenant_id"],
                         date.fromisoformat(i["period_start"]), date.fromisoformat(i["period_end"]),
                         tx["business_fields"]))

pv_checked = pv_equal = 0
for t, ps, pe in cases:
    o, m = ora_preview(t, ps, pe), mongo_preview(t, ps, pe)
    pv_checked += 1
    if cmp_rows(o, m): pv_equal += 1
    else: out["failures"].append(f"preview:{t}:{ps}:{o}!={m}")
out["invoice_preview"] = {"checked": pv_checked, "equal": pv_equal}

tx_checked = tx_equal = 0
for scen, t, ps, pe, bf in tx_cases:
    o, m = ora_preview(t, ps, pe), mongo_preview(t, ps, pe)
    def q2(x): return None if x is None else Decimal(x if not isinstance(x, Decimal128) else x.to_decimal()).quantize(Decimal("0.01"), ROUND_HALF_UP)
    ok = cmp_rows(o, m)
    if "amounts" in bf: ok = ok and [q2(r[3]) for r in m] == [Decimal(a) for a in bf["amounts"]]
    if "totals" in bf: ok = ok and [q2(r[6]) for r in m] == [Decimal(a) for a in bf["totals"]]
    if "line_numbers" in bf: ok = ok and [r[0] for r in m] == bf["line_numbers"]
    if "line_types" in bf: ok = ok and [r[1] for r in m] == bf["line_types"]
    if "tax_amount" in bf: ok = ok and [q2(r[4]) for r in m] == [Decimal(a) for a in bf["tax_amount"]]
    tx_checked += 1
    if ok: tx_equal += 1
    else: out["failures"].append(f"transcript:{scen}:{[q2(r[3]) for r in m]}; bf={bf}")
out["transcripts"] = {"checked": tx_checked, "equal": tx_equal}

# ---- fn_invoice_lines SQL vs service.invoice_lines ----
cur.execute("select id from invoices")
inv_ids = [r[0] for r in cur.fetchall()] + ["no-such-invoice"]
il_checked = il_equal = 0
for iid in inv_ids:
    cur.execute("""SELECT line_no, line_type, description, amount FROM invoice_lines
                    WHERE invoice_id = :i ORDER BY line_no""", i=iid)
    o = [[norm(x) for x in r] for r in cur.fetchall()]
    m = [[norm(r[k]) for k in ("line_no", "line_type", "description", "amount")]
         for r in svc.invoice_lines(iid)]
    il_checked += 1
    if o == m: il_equal += 1
    else: out["failures"].append(f"invoice_lines:{iid}:{o}!={m}")
out["invoice_lines"] = {"checked": il_checked, "equal": il_equal}

json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
print("failures:", len(out["failures"]))
print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=1))
print("\n".join(str(f) for f in out["failures"][:10]))
