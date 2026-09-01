"""Wave 2 app-level query replay: legacy SQL (read-only, verbatim from the PL/SQL
bodies — the packages themselves are never invoked because log_msg writes) vs the
units' own migrated services (plans_service.py, rating_service.py).
"""
import json, os, sys
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

import oracledb
from pymongo import MongoClient
from bson.decimal128 import Decimal128

sys.path.insert(0, os.path.expanduser("~/wave_recon/wt-u3/scripts/tp_mongo"))
import plans_service
sys.path.insert(0, os.path.expanduser("~/wave_recon/wt-u4/scripts/tp_mongo"))
import rating_service

oracledb.defaults.fetch_decimals = True
USER, PWD, DSN = os.environ["OW_BILLING_FIXTURE_DSN"].split("/", 2)
ora = oracledb.connect(user=USER, password=PWD, dsn=DSN)
cur = ora.cursor()
mc = MongoClient(os.environ["MONGODB_ATLAS_URI"])
db = mc["ow_tp_mongodb_032752"]
out = {"failures": []}

def norm(v):
    if isinstance(v, Decimal128): v = v.to_decimal()
    if isinstance(v, bool): return v
    if isinstance(v, int): v = Decimal(v)
    if isinstance(v, Decimal):
        s = format(v, "f")
        return s.rstrip("0").rstrip(".") if "." in s else s
    if isinstance(v, datetime): return v.replace(tzinfo=None).isoformat()
    if isinstance(v, date): return datetime(v.year, v.month, v.day).isoformat()
    return v

# ---- U3: fn_list_plans SQL vs plans_service.list_plans ----
cur.execute("""
  SELECT id AS plan_id, code,
         DECODE(tier_cd,1,'starter',2,'growth',3,'scale','UNKNOWN') AS tier,
         monthly_fee, included_units, overage_rate
    FROM plans WHERE NVL(active_yn,'N')='Y' ORDER BY monthly_fee, code""")
ora_plans = [[norm(x) for x in r] for r in cur.fetchall()]
mongo_plans = [[norm(p[k]) for k in ("plan_id", "code", "tier", "monthly_fee",
                                     "included_units", "overage_rate")]
               for p in plans_service.list_plans(db)]
out["list_plans"] = {"ora_rows": len(ora_plans), "mongo_rows": len(mongo_plans),
                     "equal": ora_plans == mongo_plans}
if not out["list_plans"]["equal"]: out["failures"].append("list_plans")

# ---- U3: fn_entitlement SQL vs plans_service.entitlement ----
cur.execute("select distinct tenant_id from subscriptions")
tenants = [r[0] for r in cur.fetchall()]
probe_dates = [datetime(2025, 6, 15), datetime(2024, 1, 1), datetime(2026, 8, 31)]
ENT_SQL = """
  SELECT * FROM (
    SELECT t.id AS tenant_id, p.code AS plan_code,
           DECODE(p.tier_cd,1,'starter',2,'growth',3,'scale','UNKNOWN') AS tier,
           p.monthly_fee, p.included_units,
           DECODE(s.status_cd,10,'active',20,'suspended',30,'cancelled','UNKNOWN') AS subscription_status,
           GREATEST(s.starts_on, :p_on) AS effective_on
      FROM tenants t, subscriptions s, plans p
     WHERE s.tenant_id = t.id AND p.id (+) = s.plan_id AND t.id = :p_tenant
       AND s.starts_on <= :p_on AND (s.ends_on IS NULL OR s.ends_on >= :p_on)
     ORDER BY s.starts_on DESC
  ) WHERE ROWNUM <= 1"""
ent_checked = ent_equal = 0
for t in tenants + ["no-such-tenant", ""]:
    for on in probe_dates:
        cur.execute(ENT_SQL, p_tenant=t, p_on=on)
        row = cur.fetchone()
        ora_e = None if row is None else [norm(x) for x in row]
        m = plans_service.entitlement(db, t, on)
        mongo_e = None if m is None else [norm(m[k]) for k in
            ("tenant_id", "plan_code", "tier", "monthly_fee", "included_units",
             "subscription_status", "effective_on")]
        ent_checked += 1
        if ora_e == mongo_e: ent_equal += 1
        else: out["failures"].append(f"entitlement:{t}@{on.date()}:{ora_e}!={mongo_e}")
out["entitlement"] = {"checked": ent_checked, "equal": ent_equal}

# ---- U4: fn_usage_summary SQL vs RatingService.usage_summary ----
svc = rating_service.RatingService(db)
cur.execute("select distinct tenant_id from usage_events")
ue_tenants = [r[0] for r in cur.fetchall()]
windows = [(date(2025, 1, 1), date(2025, 3, 31)), (date(2025, 6, 1), date(2025, 6, 30)),
           (date(2020, 1, 1), date(2020, 1, 31))]
cur.execute("select tenant_id, period_start, period_end from rating_periods")
period_rows = [(r[0], r[1].date(), r[2].date()) for r in cur.fetchall()]
us_checked = us_equal = 0
for t in ue_tenants[:25] + ["no-such-tenant"]:
    for ws, we in windows:
        cur.execute("""
          SELECT DECODE(u.kind_cd,1,'api',2,'storage',3,'compute','UNKNOWN') AS kind,
                 COUNT(*) AS event_count, NVL(SUM(u.units),0) AS units
            FROM usage_events u
           WHERE u.tenant_id = :t
             AND TO_CHAR(u.occurred_at,'YYYYMMDD')
                 BETWEEN TO_CHAR(:ws,'YYYYMMDD') AND TO_CHAR(:we,'YYYYMMDD')
           GROUP BY DECODE(u.kind_cd,1,'api',2,'storage',3,'compute','UNKNOWN')
           ORDER BY 1""", t=t, ws=datetime.combine(ws, datetime.min.time()),
                       we=datetime.combine(we, datetime.min.time()))
        ora_s = [(r[0], int(r[1]), int(r[2])) for r in cur.fetchall()]
        mongo_s = [(r["kind"], r["event_count"], r["units"])
                   for r in svc.usage_summary(t, ws, we)]
        us_checked += 1
        if ora_s == mongo_s: us_equal += 1
        else: out["failures"].append(f"usage_summary:{t}:{ws}:{ora_s}!={mongo_s}")
out["usage_summary"] = {"checked": us_checked, "equal": us_equal}

# ---- U4: compute_rating replicated from PL/SQL (read-only) vs RatingService ----
def ora_compute(t, ps, pe):
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
    prior = min(2 * included, prior) if included is not None else prior
    quota = included
    rollover = min(prior, included * 2) if included is not None else prior
    billable = max(used - rollover - included, 0) if included is not None else 0
    first = min(billable, 101); second = max(billable - 101, 0)
    overage = None if rate is None else (Decimal(first) * rate +
              Decimal(second) * rate * Decimal("1.5")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if v_sub_status == 20 and v_susp is not None and psd <= v_susp <= ped:
        factor = Decimal((ped - v_susp).days + 1) / Decimal((ped - psd).days + 1)
        billable = int((Decimal(billable) * factor).quantize(Decimal(1), ROUND_HALF_UP))
        overage = None if overage is None else (overage * factor).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return (int(used), quota if quota is None else int(quota),
            rollover if rollover is None else int(rollover), int(billable),
            int(first), int(second), None if overage is None else str(overage))

cr_checked = cr_equal = 0
cases = period_rows + [(t, date(2025, 4, 1), date(2025, 4, 30)) for t in ue_tenants[:15]]
cases += [(t, date(2025, 8, 1), date(2025, 8, 31)) for t in tenants[:10]]
# targeted: the one suspended subscription, with windows covering suspended_on
cur.execute("select tenant_id, suspended_on from subscriptions where suspended_on is not null")
for st, so in cur.fetchall():
    sod = so.date()
    cases += [(st, sod.replace(day=1), (sod.replace(day=1) + __import__("datetime").timedelta(days=40)).replace(day=1) - __import__("datetime").timedelta(days=1)),
              (st, sod - __import__("datetime").timedelta(days=10), sod + __import__("datetime").timedelta(days=10)),
              (st, sod, sod)]
for t, ps, pe in cases:
    o = ora_compute(t, ps, pe)
    r = svc.compute_rating(t, ps, pe)
    m = (r.used_units, r.quota_units, r.rollover_units, r.billable_units,
         r.first_tier_units, r.second_tier_units,
         None if r.overage_amount is None else str(r.overage_amount))
    cr_checked += 1
    if o == m: cr_equal += 1
    else: out["failures"].append(f"compute_rating:{t}:{ps}:{o}!={m}")
out["compute_rating"] = {"checked": cr_checked, "equal": cr_equal}

json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
print("failures:", len(out["failures"]))
print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=1))
print("\n".join(out["failures"][:10]))
