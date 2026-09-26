"""Unit dunning: DUNNING_ATTEMPTS / NOTIFICATIONS (wave 1).

Ports (db/oracle/packages/05_pkg_dunning.sql, facade.py):
- pkg_dunning.fn_overdue_accounts -> overdue(): invoices(status 40, issued before as_of) x tenants(+)
- pkg_dunning.sp_schedule_dunning -> schedule_dunning(): per overdue invoice, next attempt_no,
                                     weekend roll-forward, insert-or-ignore (unique invoiceId+attemptNo).
                                     g_last_run_dt / g_scheduled_cnt globals -> the returned value.
- pkg_dunning.sp_suspend_overdue  -> suspend_overdue(): tenants 14+ days overdue and still active:
                                     tenant status 20, active subscriptions suspended, one
                                     'suspension' notification per tenant per day (unique index).
- facade GET /admin/dunning       -> list_attempts(): attempts scheduled on/before as_of x codes(DUN_STATUS)

Writes dunning_attempts and notifications (this unit). suspend_overdue also writes
subscriptions (unit subscriptions_rating, same batch) and tenants (wave-0 collection,
NOT a w1-b03 write target): that update is implemented for behavioural parity but is a
plan gap to record; it is never executed by the migration load or recon.
"""
from dataclasses import dataclass
from datetime import timedelta

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from . import db
from . import shared_reference
from ._util import TENANT_STATUS, md5_uuid, num_out, trunc, ymd

INV_STATUS_OVERDUE = 40
DUN_STATUS_SCHEDULED = 10
NOTIFY_SUSPENSION = 3
WEEKEND_ROLL = {5: 2, 6: 1}  # Python weekday(): SAT -> +2, SUN -> +1 (DECODE(TO_CHAR(d,'DY')))


def overdue(as_of):
    """pkg_dunning.fn_overdue_accounts."""
    day = trunc(as_of)
    out = []
    cursor = db().invoices.find(
        {"statusCd": INV_STATUS_OVERDUE, "issuedAt": {"$lt": day}}
    ).sort([("issuedAt", ASCENDING), ("_id", ASCENDING)])
    for inv in cursor:
        tenant = db().tenants.find_one({"_id": inv.get("tenantId")}, {"statusCd": 1}) or {}
        out.append({
            "tenant_id": inv.get("tenantId"),
            "invoice_id": inv["_id"],
            "total": num_out(inv.get("total")),
            "days_overdue": (day - trunc(inv["issuedAt"])).days,
            "tenant_status": TENANT_STATUS.get(tenant.get("statusCd"), "UNKNOWN"),
        })
    return out


@dataclass
class DunningRun:
    """pkg_dunning g_last_run_dt / g_scheduled_cnt as a returned value."""
    last_run_dt: object
    scheduled_cnt: int = 0


def next_business_day(day):
    day = trunc(day)
    return day + timedelta(days=WEEKEND_ROLL.get(day.weekday(), 0))


def schedule_dunning(as_of):
    """pkg_dunning.sp_schedule_dunning."""
    run = DunningRun(last_run_dt=as_of)
    scheduled_for = next_business_day(as_of)
    attempts = db().dunning_attempts
    invoices = db().invoices.find(
        {"statusCd": INV_STATUS_OVERDUE}, {"tenantId": 1}
    ).sort([("issuedAt", ASCENDING), ("_id", ASCENDING)])
    for inv in invoices:
        last = attempts.find_one({"invoiceId": inv["_id"]}, {"attemptNo": 1}, sort=[("attemptNo", DESCENDING)])
        attempt_no = (last["attemptNo"] if last else 0) + 1
        attempt_id = md5_uuid(f"{inv['_id']}{attempt_no}")
        try:
            attempts.insert_one({
                "_id": attempt_id, "id": attempt_id, "tenantId": inv.get("tenantId"),
                "invoiceId": inv["_id"], "attemptNo": attempt_no,
                "scheduledFor": scheduled_for, "statusCd": DUN_STATUS_SCHEDULED,
            })
            run.scheduled_cnt += 1
        except DuplicateKeyError:  # WHEN OTHERS THEN NULL (ON CONFLICT DO NOTHING)
            continue
    return run


def suspend_overdue(as_of):
    """pkg_dunning.sp_suspend_overdue. Returns the tenant ids suspended."""
    day = trunc(as_of)
    cutoff = day - timedelta(days=14)
    tenant_ids = db().invoices.distinct(
        "tenantId", {"statusCd": INV_STATUS_OVERDUE, "issuedAt": {"$lt": cutoff + timedelta(days=1)}}
    )
    suspended = []
    for tenant_id in tenant_ids:
        # tenants is a wave-0 collection: the status flip is part of the ported behaviour, not
        # of this batch's write targets (see module docstring / PR "Unverified paths").
        res = db().tenants.update_one({"_id": tenant_id, "statusCd": 10}, {"$set": {"statusCd": 20}})
        if res.matched_count == 0:
            continue
        db().subscriptions.update_many(
            {"tenantId": tenant_id, "statusCd": 10},
            {"$set": {"statusCd": 20, "suspendedOn": day}},
        )
        note_id = md5_uuid(f"{tenant_id}suspension{ymd(day)}")
        try:  # NOT EXISTS (tenant, kind, sent_at) -> unique index {tenantId, kindCd, sentAt}
            db().notifications.insert_one({
                "_id": note_id, "id": note_id, "tenantId": tenant_id,
                "kindCd": NOTIFY_SUSPENSION, "sentAt": day,
            })
        except DuplicateKeyError:
            pass
        suspended.append(tenant_id)
    return suspended


def list_attempts(as_of, limit=200):
    """facade GET /admin/dunning."""
    cursor = db().dunning_attempts.find(
        {"scheduledFor": {"$lte": trunc(as_of)}}
    ).sort([("scheduledFor", DESCENDING), ("_id", DESCENDING)]).limit(limit)
    out = []
    for d in cursor:
        status = (shared_reference.code_desc("DUN_STATUS", d.get("statusCd"))
                  if d.get("statusCd") is not None else None)
        out.append({"id": d["_id"], "tenant_id": d.get("tenantId"), "invoice_id": d.get("invoiceId"),
                    "attempt_no": d.get("attemptNo"), "scheduled_for": d.get("scheduledFor"),
                    "status": status})
    return out
