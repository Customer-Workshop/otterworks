"""Unit subscriptions_rating: SUBSCRIPTIONS / USAGE_EVENTS / RATING_PERIODS(+results[]) (wave 1).

Ports (db/oracle/packages/02_pkg_plans.sql, 03_pkg_rating.sql, backends/oracle.py, facade.py):
- pkg_plans.fn_entitlement            -> entitlement(): covering subscription + plan point reads
- pkg_plans.sp_change_plan            -> change_plan(): FOR UPDATE row loop -> find_one_and_update
                                         loop (pipeline update keeps the DECODE(status_cd,30,30,10)
                                         rule per row), then insert the new subscription
- pkg_rating.compute_rating           -> compute_rating(): package globals -> a Rating value
                                         returned to the caller (request-scoped state)
- pkg_rating.fn_usage_rating          -> usage_rating()
- pkg_rating.fn_usage_summary         -> usage_summary(): $group by kind
- pkg_rating.sp_finalize_rating       -> finalize_rating(): period upsert + results[] element
                                         upsert on one rating_periods document
- facade /usage events list, /internal/usage/events insert -> list_usage_events(), record_usage_event()

Reads plans (wave-0 collection) read-only. Writes only subscriptions, usage_events, rating_periods.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from bson.int64 import Int64
from pymongo import DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import db
from . import shared_reference
from ._util import (SUB_STATUS, TIER_LABELS, USAGE_KIND, as_datetime, day_ceiling, dec, md5_uuid,
                    money, num_out, oround, plain, strip_none, trunc, ymd)

TIER_BREAK = 101  # "Why 101? Nobody remembers." (pkg_rating.compute_rating)


# ---------------------------------------------------------------- pkg_plans

def covering_subscription(tenant_id, start, end):
    """Latest subscription overlapping [start, end]: starts_on <= end AND (ends_on IS NULL OR ends_on >= start)."""
    return db().subscriptions.find_one(
        {
            "tenantId": tenant_id,
            "startsOn": {"$lte": as_datetime(end)},
            "$or": [{"endsOn": None}, {"endsOn": {"$gte": as_datetime(start)}}],
        },
        sort=[("startsOn", DESCENDING)],
    )


def entitlement(tenant_id, on):
    """pkg_plans.fn_entitlement: one row or none (tenants x subscriptions x plans(+))."""
    on_dt = as_datetime(on)
    if db().tenants.find_one({"_id": tenant_id}, {"_id": 1}) is None:
        return []
    sub = covering_subscription(tenant_id, on_dt, on_dt)
    if sub is None:
        return []
    plan = db().plans.find_one({"_id": sub.get("planId")}) if sub.get("planId") else None
    plan = plan or {}
    return [{
        "tenant_id": tenant_id,
        "plan_code": plan.get("code"),
        "tier": TIER_LABELS.get(plan.get("tierCd"), "UNKNOWN"),
        "monthly_fee": num_out(plan.get("monthlyFee")),
        "included_units": plan.get("includedUnits"),
        "subscription_status": SUB_STATUS.get(sub.get("statusCd"), "UNKNOWN"),
        "effective_on": max(sub["startsOn"], on_dt),
    }]


_CLOSE_OUT = [{"$set": {"statusCd": {"$cond": [{"$eq": ["$statusCd", 30]}, 30, 10]}}}]


def _close_open_subscriptions(tenant_id, effective_on, starts_filter):
    """One FOR UPDATE ... WHERE CURRENT OF row at a time -> findOneAndUpdate until none match."""
    closed = 0
    while True:
        doc = db().subscriptions.find_one_and_update(
            {"tenantId": tenant_id, "endsOn": None, "startsOn": starts_filter},
            [{"$set": {"endsOn": effective_on - timedelta(days=1)}}] + _CLOSE_OUT,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            return closed
        closed += 1


def change_plan(tenant_id, plan_id, effective_on):
    """backends/oracle.change_plan + pkg_plans.sp_change_plan.

    1. oracle.py pre-step: close same-day open subscriptions (starts_on = eff).
    2. sp_change_plan: close open subscriptions with starts_on < eff, row by row.
    3. insert the new subscription (id = md5(tenant || plan || YYYY-MM-DD), status 10).
    The 'cancelled stays cancelled' rule (TRG_SUB_NO_UNCANCEL) is the DECODE in the pipeline.
    """
    eff = trunc(effective_on)
    _close_open_subscriptions(tenant_id, eff, eff)
    _close_open_subscriptions(tenant_id, eff, {"$lt": eff})
    new_id = md5_uuid(f"{tenant_id}{plan_id}{ymd(eff)}")
    db().subscriptions.insert_one(
        {"_id": new_id, "id": new_id, "tenantId": tenant_id, "planId": plan_id,
         "startsOn": eff, "statusCd": 10}
    )
    return new_id


# --------------------------------------------------------------- pkg_rating

@dataclass
class Rating:
    """pkg_rating package globals g_* as a request-scoped value."""
    tenant_id: str
    period_start: object
    period_end: object
    used_units: int = 0
    quota_units: Optional[int] = None
    rollover_units: Optional[int] = None
    billable_units: Optional[int] = None
    first_tier: Optional[int] = None
    second_tier: Optional[int] = None
    overage_amount: Optional[Decimal] = None
    subscription: Optional[dict] = None

    def as_row(self):
        return {
            "tenant_id": self.tenant_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "used_units": self.used_units,
            "quota_units": self.quota_units,
            "rollover_units": self.rollover_units,
            "billable_units": self.billable_units,
            "first_tier_units": self.first_tier,
            "second_tier_units": self.second_tier,
            "overage_amount": num_out(self.overage_amount),
        }


def _add_months(d, months):
    """Oracle ADD_MONTHS: same day-of-month, clamped to the target month's length
    (and last-day-of-month maps to last-day-of-month)."""
    import calendar
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    last_src = calendar.monthrange(d.year, d.month)[1]
    last_dst = calendar.monthrange(y, m)[1]
    day = last_dst if d.day == last_src else min(d.day, last_dst)
    return d.replace(year=y, month=m, day=day)


def _sum_usage(tenant_id, start, end):
    """SUM(units) where TO_CHAR(occurred_at,'YYYYMMDD') between the period days."""
    agg = list(db().usage_events.aggregate([
        {"$match": {"tenantId": tenant_id,
                    "occurredAt": {"$gte": trunc(start), "$lt": day_ceiling(end)}}},
        {"$group": {"_id": None, "units": {"$sum": {"$ifNull": ["$units", 0]}}}},
    ]))
    return int(agg[0]["units"]) if agg else 0


def _prior_rollover(tenant_id, period_start):
    """SUM(rating_results.rollover_units) over the prior three months of periods."""
    start = trunc(period_start)
    agg = list(db().rating_periods.aggregate([
        {"$match": {"tenantId": tenant_id,
                    "periodStart": {"$lt": start, "$gte": _add_months(start, -3)}}},
        {"$unwind": "$results"},
        {"$group": {"_id": None, "units": {"$sum": {"$ifNull": ["$results.rolloverUnits", 0]}}}},
    ]))
    return int(agg[0]["units"]) if agg else 0


def compute_rating(tenant_id, period_start, period_end):
    """pkg_rating.compute_rating, NULL semantics preserved (Oracle LEAST/GREATEST propagate NULL;
    the package collapses them with NVL exactly where the original did)."""
    start, end = trunc(period_start), trunc(period_end)
    r = Rating(tenant_id, start, end)
    sub = covering_subscription(tenant_id, start, end)
    r.subscription = sub
    included = rate = None
    if sub is not None and sub.get("planId"):
        plan = db().plans.find_one({"_id": sub["planId"]})
        if plan:
            included = plan.get("includedUnits")
            rate = dec(plan.get("overageRate"))

    r.used_units = _sum_usage(tenant_id, start, end)

    prior = _prior_rollover(tenant_id, start)
    prior = prior if included is None else min(2 * included, prior)

    r.quota_units = included
    r.rollover_units = prior if included is None else min(prior, included * 2)
    billable = None if included is None else r.used_units - r.rollover_units - included
    r.billable_units = max(billable if billable is not None else 0, 0)
    r.first_tier = min(r.billable_units, TIER_BREAK)
    r.second_tier = max(r.billable_units - TIER_BREAK, 0)
    if rate is not None:
        r.overage_amount = oround(r.first_tier * rate + r.second_tier * rate * Decimal("1.5"), 2)

    susp = sub.get("suspendedOn") if sub else None
    if sub and sub.get("statusCd") == 20 and susp is not None and start <= susp <= end:
        factor = Decimal((end - susp).days + 1) / Decimal((end - start).days + 1)
        r.billable_units = int(oround(Decimal(r.billable_units) * factor, 0))
        r.overage_amount = oround(r.overage_amount * factor, 2) if r.overage_amount is not None else None
    return r


def usage_rating(tenant_id, start, end):
    """pkg_rating.fn_usage_rating: one row."""
    return [compute_rating(tenant_id, start, end).as_row()]


def usage_summary(tenant_id, start, end):
    """pkg_rating.fn_usage_summary: per-kind count/sum ordered by kind label."""
    rows = db().usage_events.aggregate([
        {"$match": {"tenantId": tenant_id,
                    "occurredAt": {"$gte": trunc(start), "$lt": day_ceiling(end)}}},
        {"$group": {"_id": "$kindCd", "event_count": {"$sum": 1},
                    "units": {"$sum": {"$ifNull": ["$units", 0]}}}},
    ])
    by_kind = {}
    for row in rows:  # DECODE collapses unknown codes onto one 'UNKNOWN' group
        kind = USAGE_KIND.get(row["_id"], "UNKNOWN")
        acc = by_kind.setdefault(kind, {"kind": kind, "event_count": 0, "units": 0})
        acc["event_count"] += row["event_count"]
        acc["units"] += int(row["units"])
    return [by_kind[k] for k in sorted(by_kind)]


def finalize_rating(tenant_id, period_start, period_end):
    """pkg_rating.sp_finalize_rating as one rating_periods document:
    period upsert (INSERT / DUP_VAL_ON_INDEX -> UPDATE period_end by tenant+period_start),
    then the RATING_RESULTS row as an element upsert in results[] keyed by id = md5(period_id)."""
    start, end = trunc(period_start), trunc(period_end)
    period_id = md5_uuid(f"{tenant_id}{ymd(start)}")
    periods = db().rating_periods
    sub = covering_subscription(tenant_id, start, end)

    try:
        periods.update_one(
            {"_id": period_id},
            {"$setOnInsert": {"id": period_id, "tenantId": tenant_id, "periodStart": start, "results": []},
             "$set": {"periodEnd": end}},
            upsert=True,
        )
    except DuplicateKeyError:  # unique {tenantId, periodStart} held by another _id
        periods.update_one({"tenantId": tenant_id, "periodStart": start}, {"$set": {"periodEnd": end}})
        period_id = periods.find_one({"tenantId": tenant_id, "periodStart": start}, {"_id": 1})["_id"]

    r = compute_rating(tenant_id, start, end)
    result_id = md5_uuid(period_id)
    stored_rollover = None if r.quota_units is None else max(r.quota_units - r.used_units, 0)
    values = strip_none({
        "subscriptionId": sub["_id"] if sub else None,
        "usedUnits": Int64(r.used_units),
        "quotaUnits": None if r.quota_units is None else Int64(r.quota_units),
        "rolloverUnits": None if stored_rollover is None else Int64(stored_rollover),
        "billableUnits": None if r.billable_units is None else Int64(r.billable_units),
        "overageAmount": money(r.overage_amount),
    })
    # UPDATE path (existing element): the original only refreshes used/rollover/billable/overage.
    upd = periods.update_one(
        {"_id": period_id, "results.id": result_id},
        {"$set": {f"results.$.{k}": v for k, v in values.items()
                  if k in ("usedUnits", "rolloverUnits", "billableUnits", "overageAmount")}},
    )
    if upd.matched_count == 0:  # INSERT path
        elem = {"id": result_id, "periodId": period_id, **values, "createdAt": end}
        periods.update_one({"_id": period_id}, {"$push": {"results": elem}})
    return period_id


# ------------------------------------------------------- usage events (facade)

def list_usage_events(tenant_id, start, end, limit=50):
    """facade GET /usage events: latest 50 in [start, end] with the USAGE_KIND description."""
    cursor = db().usage_events.find(
        {"tenantId": tenant_id, "occurredAt": {"$gte": trunc(start), "$lt": day_ceiling(end)}}
    ).sort([("occurredAt", DESCENDING), ("_id", DESCENDING)]).limit(limit)
    out = []
    for e in cursor:
        kind = shared_reference.code_desc("USAGE_KIND", e.get("kindCd")) if e.get("kindCd") is not None else None
        if kind is None:  # the Oracle query is an inner JOIN on codes
            continue
        out.append({"id": e["_id"], "occurred_at": e.get("occurredAt"),
                    "units": plain(e.get("units")), "kind": kind})
    return out


def record_usage_event(event_id, tenant_id, occurred_at, units, kind):
    """facade POST /internal/usage/events: kind resolved via CODES(USAGE_KIND) by description.
    Returns 'recorded' or 'duplicate' (ORA-00001 -> DuplicateKeyError on _id)."""
    kind_cd = shared_reference.code_val("USAGE_KIND", kind) if kind else None
    doc = strip_none({"_id": event_id, "id": event_id, "tenantId": tenant_id,
                      "occurredAt": as_datetime(occurred_at),
                      "units": None if units is None else Int64(units),
                      "kindCd": kind_cd})
    try:
        db().usage_events.insert_one(doc)
    except DuplicateKeyError:
        return "duplicate"
    return "recorded"
