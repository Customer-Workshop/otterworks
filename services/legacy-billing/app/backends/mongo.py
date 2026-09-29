"""MongoDB backend: the OW_BILLING estate served from the map-1 collections.

Every operation mirrors backends/oracle.py and the PL/SQL packages it calls
(pkg_plans, pkg_rating, pkg_invoicing, pkg_dunning, pkg_ow_util) plus the
schema triggers (subscription history, no-uncancel, usage checks). Rows are
rendered the way oracle.rows() renders an Oracle cursor: NUMBER as canonical
Decimal text, midnight DATE values as ISO dates.
"""

import hashlib
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from uuid import NAMESPACE_URL, uuid5

from bson.decimal128 import Decimal128
from bson.int64 import Int64
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

NAME = "mongo"
ERRORS = (PyMongoError,)

_URI = os.getenv("BILLING_MONGO_URI")
if not _URI:
    raise RuntimeError("BILLING_MONGO_URI is required when BILLING_BACKEND=mongo")
DB_NAME = os.getenv("BILLING_MONGO_DB", "ow_tp_mmp_live")

_client = MongoClient(_URI, tz_aware=False, appname="legacy-billing")
db = _client[DB_NAME]

TAX_RATE = Decimal("0.0825")
TIER_BREAK = Decimal(101)
_NUMBER = Context(prec=40)
_MON = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_TIERS = {1: "starter", 2: "growth", 3: "scale"}
_SUB_STATUS = {10: "active", 20: "suspended", 30: "cancelled"}
_TENANT_STATUS = {10: "active", 20: "suspended"}
_USAGE_KIND = {1: "api", 2: "storage", 3: "compute"}
_LINE_TYPE = {1: "CHARGE", 2: "CREDIT", 3: "ADJUSTMENT", 9: "MISC"}

CUSTOMER_COLUMNS = (
    'cust_id', 'cust_seq_no', 'tenant_id', 'cust_no', 'cust_name', 'cust_name_upper',
    'legal_name', 'dba_name', 'addr_line_1', 'addr_line_2', 'addr_line_3',
    'addr_line_4', 'addr_line_5', 'addr_line_6', 'city', 'state_cd', 'zip', 'zip4',
    'country_cd', 'mail_addr_line_1', 'mail_addr_line_2', 'mail_addr_line_3',
    'mail_addr_line_4', 'mail_addr_line_5', 'mail_addr_line_6', 'mail_city',
    'mail_state_cd', 'mail_zip', 'phone1', 'phone2', 'phone3', 'phone4',
    'phone1_type_cd', 'phone2_type_cd', 'phone3_type_cd', 'phone4_type_cd', 'fax',
    'email_1', 'email_2', 'email_3', 'signup_dt', 'last_activity_dt', 'last_invoice_dt',
    'last_payment_dt', 'terminate_dt', 'status_cd', 'sub_status_cd', 'cust_type_cd',
    'segment_cd', 'region_cd', 'territory_cd', 'channel_cd', 'rate_class_cd',
    'tax_exempt_yn', 'credit_hold_yn', 'dunning_exempt_yn', 'vip_yn', 'cur_bal_amt',
    'past_due_amt', 'ytd_billed_amt', 'ltd_billed_amt', 'ytd_paid_amt',
    'credit_limit_amt', 'related_acct_ids', 'child_acct_ids', 'promo_codes_csv',
    'contact_notes', 'legacy_sys_key', 'mainframe_acct_no', 'conversion_batch_no',
    'flag_01', 'flag_02', 'flag_03', 'flag_04', 'flag_05', 'flag_06', 'flag_07',
    'flag_08', 'flag_09', 'flag_10', 'flag_11', 'flag_12', 'flag_13', 'flag_14',
    'flag_15', 'flag_16', 'flag_17', 'flag_18', 'flag_19', 'flag_20', 'udf_01',
    'udf_02', 'udf_03', 'udf_04', 'udf_05', 'udf_06', 'udf_07', 'udf_08', 'udf_09',
    'udf_10', 'udf_11', 'udf_12', 'udf_13', 'udf_14', 'udf_15', 'udf_16', 'udf_17',
    'udf_18', 'udf_19', 'udf_20', 'udf_21', 'udf_22', 'udf_23', 'udf_24', 'udf_25',
    'udf_26', 'udf_27', 'udf_28', 'udf_29', 'udf_30', 'udf_31', 'udf_32', 'udf_33',
    'udf_34', 'udf_35', 'udf_36', 'udf_37', 'udf_38', 'udf_39', 'udf_40', 'udf_amt_01',
    'udf_amt_02', 'udf_amt_03', 'udf_amt_04', 'udf_amt_05', 'udf_amt_06', 'udf_amt_07',
    'udf_amt_08', 'udf_amt_09', 'udf_amt_10', 'udf_dt_01', 'udf_dt_02', 'udf_dt_03',
    'udf_dt_04', 'udf_dt_05', 'udf_dt_06', 'udf_dt_07', 'udf_dt_08', 'udf_dt_09',
    'udf_dt_10', 'created_by', 'created_dt', 'updated_by', 'updated_dt',
    'row_version_no',
)
ATTRIBUTE_COLUMNS = (
    "eav_id", "entity_type", "entity_id", "attr_name", "attr_value", "attr_type", "created_dt",
)


class BackendError(PyMongoError):
    """A statement the Oracle estate would have rejected (constraint, NOT NULL)."""


class UsageRejected(BackendError):
    """The TRG_USAGE_EVENTS_CHECK rejections (ORA-20001 / ORA-20002)."""


# ---------------------------------------------------------------- values


def _dec(value):
    if value is None:
        return None
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("boolean is not a NUMBER")
    if isinstance(value, int):
        return Decimal(value)
    raise TypeError(f"expected a NUMBER value, got {type(value).__name__}")


def _canon(value):
    """Oracle NUMBER -> Decimal the way oracledb fetch_decimals returns it."""
    if value is None:
        return None
    number = _dec(value)
    if number == 0:
        return Decimal(0)
    number = number.normalize(_NUMBER)
    if number == number.to_integral_value():
        return number.quantize(Decimal(1))
    return number


def _d128(value):
    return None if value is None else Decimal128(_canon(value))


def _round(value, places=0):
    if value is None:
        return None
    exponent = Decimal(1).scaleb(-places)
    return _dec(value).quantize(exponent, rounding=ROUND_HALF_UP, context=_NUMBER)


def _json_value(value):
    if isinstance(value, datetime):
        if value.time() == time.min:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (Decimal, Decimal128, Int64)) or (
        isinstance(value, int) and not isinstance(value, bool)
    ):
        return str(_canon(value))
    return value


def _row(pairs):
    return {name: _json_value(value) for name, value in pairs}


def _to_char(value):
    """TO_CHAR(<NUMBER>) with the default format: no leading zero before '.'."""
    text = str(_canon(value))
    if text.startswith("0."):
        return text[1:]
    if text.startswith("-0."):
        return "-" + text[2:]
    return text


def _fm_money(value):
    """TO_CHAR(n, 'FM999999999999990.00')."""
    if value is None:
        return None
    return str(_round(value, 2))


def _day(value):
    """TRUNC(<date>) as a naive midnight datetime (BSON has no DATE type)."""
    if isinstance(value, datetime):
        return datetime.combine(value.date(), time.min)
    return datetime.combine(_as_date(value), time.min)


def _add_months(day, months):
    month_index = day.year * 12 + day.month - 1 + months
    year, month = divmod(month_index, 12)
    month += 1
    first_next = date(year + (month == 12), month % 12 + 1, 1)
    last_day = (first_next - timedelta(days=1)).day
    this_last = (date(day.year + (day.month == 12), day.month % 12 + 1, 1) - timedelta(days=1)).day
    if day.day == this_last or day.day > last_day:
        return datetime(year, month, last_day)
    return datetime(year, month, day.day)


def _dd_mon_yy(day):
    return f"{day.day:02d}-{_MON[day.month - 1]}-{day.year % 100:02d}"


def _md5_uuid(text):
    digest = hashlib.md5(text.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"


def _sysdate():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _readonly():
    return os.getenv("BILLING_READONLY", "").strip().lower() in {"1", "true", "yes"}


def _clean(document):
    """NULL and '' are omitted from documents (map-1 load convention)."""
    return {key: value for key, value in document.items() if value is not None and value != ""}


# ------------------------------------------------------ audit + sequences


def _nextval(name):
    """Oracle sequences are non-transactional, so the counter never joins a session."""
    seq_id = name.upper()
    counter = db.sequences.find_one_and_update(
        {"_id": seq_id},
        {"$inc": {"value": Int64(1)}},
        return_document=ReturnDocument.AFTER,
    )
    if counter is None:
        raise BackendError(f"sequence {seq_id} is not initialised")
    return Int64(counter["value"])


def _prime_sequence(name, collection):
    """Seed a missing sequence from the collection's highest id (NOCACHE semantics)."""
    seq_id = name.upper()
    if db.sequences.find_one({"_id": seq_id}, {"_id": 1}):
        return
    top = db[collection].find_one({}, {"_id": 1}, sort=[("_id", DESCENDING)])
    start = Int64(int(top["_id"]) if top else 0)
    try:
        db.sequences.update_one(
            {"_id": seq_id}, {"$max": {"value": start}}, upsert=True
        )
    except DuplicateKeyError:
        pass


def _write_audit(entries):
    """pkg_ow_util.log_msg: autonomous insert, every failure swallowed."""
    if _readonly():
        return
    for module, message in entries:
        try:
            _prime_sequence("seq_billing_audit_log", "billing_audit_log")
            log_id = _nextval("seq_billing_audit_log")
            db.billing_audit_log.insert_one(
                _clean(
                    {
                        "_id": log_id,
                        "logged_at": _sysdate(),
                        "module": (module or "")[:30],
                        "message": (message or "")[:4000],
                    }
                )
            )
        except PyMongoError:
            continue


def log_msg(module, message):
    _write_audit([(module, message)])


def _transaction(work):
    """Run work(session, audit) in one transaction; audit rows commit regardless."""
    audit = []

    def callback(session):
        audit.clear()
        return work(session, audit)

    try:
        with _client.start_session() as session:
            return session.with_transaction(callback)
    finally:
        _write_audit(audit)


def _history(session, before):
    """TRG_SUBSCRIPTIONS_HIST: full-row copy of the OLD row on every UPDATE."""
    hist_id = _nextval("seq_subscriptions_hist")
    db.subscriptions_hist.insert_one(
        _clean(
            {
                "_id": hist_id,
                "hist_dt": f"{_dd_mon_yy(_sysdate())} {_sysdate():%H:%M:%S}",
                "hist_op": "UPD",
                "id": before["_id"],
                "tenant_id": before.get("tenant_id"),
                "plan_id": before.get("plan_id"),
                "starts_on": before.get("starts_on"),
                "ends_on": before.get("ends_on"),
                "status_cd": before.get("status_cd"),
                "suspended_on": before.get("suspended_on"),
            }
        ),
        session=session,
    )


def _update_subscription(session, before, changes):
    if before.get("status_cd") == 30 and "status_cd" in changes:
        changes = {**changes, "status_cd": 30}
    unset = {key: "" for key, value in changes.items() if value is None}
    update = {}
    values = {key: value for key, value in changes.items() if value is not None}
    if values:
        update["$set"] = values
    if unset:
        update["$unset"] = unset
    db.subscriptions.update_one({"_id": before["_id"]}, update, session=session)
    _history(session, before)


# ------------------------------------------------------------- lookups


def _codes(code_type, session=None):
    return {
        doc["code_val"]: doc["code_desc"]
        for doc in db.codes.find({"code_type": code_type}, session=session)
    }


def _code_desc(code_type, code_val, session=None):
    if code_val is None:
        return None
    doc = db.codes.find_one(
        {"code_type": code_type, "code_val": code_val}, {"code_desc": 1}, session=session
    )
    return doc.get("code_desc") if doc else None


def _covering_subscription(tenant_id, start, end, session=None):
    return db.subscriptions.find_one(
        {
            "tenant_id": tenant_id,
            "starts_on": {"$lte": _day(end)},
            "$or": [{"ends_on": None}, {"ends_on": {"$gte": _day(start)}}],
        },
        sort=[("starts_on", DESCENDING)],
        session=session,
    )


def _plan(plan_id, session=None):
    if plan_id is None:
        return None
    return db.plans.find_one({"_id": plan_id}, session=session)


def _period_window(start, end):
    return {"$gte": _day(start), "$lt": _day(end) + timedelta(days=1)}


# ------------------------------------------------------------ interface


def health():
    _client.admin.command("ping")


def list_plans():
    log_msg("PLANS", "fn_list_plans")
    plans = [plan for plan in db.plans.find() if plan.get("active_yn", "N") == "Y"]
    plans.sort(key=lambda plan: (_dec(plan["monthly_fee"]), plan["code"]))
    return [
        _row(
            [
                ("plan_id", plan["_id"]),
                ("code", plan.get("code")),
                ("tier", _TIERS.get(plan.get("tier_cd"), "UNKNOWN")),
                ("monthly_fee", plan.get("monthly_fee")),
                ("included_units", plan.get("included_units")),
                ("overage_rate", plan.get("overage_rate")),
            ]
        )
        for plan in plans
    ]


def entitlement(tenant_id, on):
    on_day = _day(on)
    if not db.tenants.find_one({"_id": tenant_id}, {"_id": 1}):
        return []
    subscription = _covering_subscription(tenant_id, on_day, on_day)
    if not subscription:
        return []
    plan = _plan(subscription.get("plan_id")) or {}
    return [
        _row(
            [
                ("tenant_id", tenant_id),
                ("plan_code", plan.get("code")),
                ("tier", _TIERS.get(plan.get("tier_cd"), "UNKNOWN")),
                ("monthly_fee", plan.get("monthly_fee")),
                ("included_units", plan.get("included_units")),
                (
                    "subscription_status",
                    _SUB_STATUS.get(subscription.get("status_cd"), "UNKNOWN"),
                ),
                ("effective_on", max(subscription["starts_on"], on_day)),
            ]
        )
    ]


def change_plan(tenant_id, plan_id, effective_on):
    effective = _day(effective_on)
    _prime_sequence("seq_subscriptions_hist", "subscriptions_hist")

    def work(session, audit):
        for before in list(
            db.subscriptions.find(
                {"tenant_id": tenant_id, "ends_on": None, "starts_on": effective},
                session=session,
            )
        ):
            _update_subscription(
                session,
                before,
                {
                    "ends_on": effective - timedelta(days=1),
                    "status_cd": 30 if before.get("status_cd") == 30 else 10,
                },
            )
        audit.append(
            (
                "PLANS",
                f"sp_change_plan tenant={tenant_id} plan={plan_id} "
                f"eff={effective:%Y-%m-%d}",
            )
        )
        for before in list(
            db.subscriptions.find(
                {"tenant_id": tenant_id, "ends_on": None, "starts_on": {"$lt": effective}},
                session=session,
            )
        ):
            _update_subscription(
                session,
                before,
                {
                    "ends_on": effective - timedelta(days=1),
                    "status_cd": 30 if before.get("status_cd") == 30 else 10,
                },
            )
        new_id = _md5_uuid(f"{tenant_id}{plan_id}{effective:%Y-%m-%d}")
        if db.subscriptions.find_one({"_id": new_id}, {"_id": 1}, session=session):
            raise BackendError(f"subscription {new_id} already exists (PK_SUBSCRIPTIONS)")
        if not db.tenants.find_one({"_id": tenant_id}, {"_id": 1}, session=session):
            raise BackendError("tenant not found (FK_SUB_TENANT)")
        if not db.plans.find_one({"_id": plan_id}, {"_id": 1}, session=session):
            raise BackendError("plan not found (FK_SUB_PLAN)")
        db.subscriptions.insert_one(
            {
                "_id": new_id,
                "tenant_id": tenant_id,
                "plan_id": plan_id,
                "starts_on": effective,
                "status_cd": 10,
            },
            session=session,
        )

    _transaction(work)


def _compute_rating(tenant_id, start, end, audit, session=None):
    start_day, end_day = _day(start), _day(end)
    subscription = _covering_subscription(tenant_id, start_day, end_day, session) or {}
    plan = _plan(subscription.get("plan_id"), session) or {}
    included = _dec(plan.get("included_units"))
    rate = _dec(plan.get("overage_rate"))

    used = Decimal(0)
    for event in db.usage_events.find(
        {"tenant_id": tenant_id, "occurred_at": _period_window(start_day, end_day)},
        {"units": 1},
        session=session,
    ):
        used += _dec(event.get("units")) or 0

    period_ids = [
        period["_id"]
        for period in db.rating_periods.find(
            {
                "tenant_id": tenant_id,
                "period_start": {"$lt": start_day, "$gte": _add_months(start_day, -3)},
            },
            {"_id": 1},
            session=session,
        )
    ]
    prior = Decimal(0)
    if period_ids:
        for result in db.rating_results.find(
            {"period_id": {"$in": period_ids}}, {"rollover_units": 1}, session=session
        ):
            prior += _dec(result.get("rollover_units")) or 0

    with localcontext(_NUMBER):
        cap = None if included is None else 2 * included
        prior = min(cap if cap is not None else prior, prior)
        rollover = min(prior, cap if cap is not None else prior)
        billable = (
            Decimal(0) if included is None else max(used - rollover - included, Decimal(0))
        )
        first_tier = min(billable, TIER_BREAK)
        second_tier = max(billable - TIER_BREAK, Decimal(0))
        overage = (
            None
            if rate is None
            else _round(first_tier * rate + second_tier * rate * Decimal("1.5"), 2)
        )
        suspended_on = subscription.get("suspended_on")
        if (
            subscription.get("status_cd") == 20
            and suspended_on is not None
            and start_day <= suspended_on <= end_day
        ):
            factor = Decimal((end_day - suspended_on).days + 1) / Decimal(
                (end_day - start_day).days + 1
            )
            billable = _round(billable * factor)
            overage = None if overage is None else _round(overage * factor, 2)

    audit.append(
        (
            "RATING",
            f"compute tenant={tenant_id} used={_to_char(used)} billable={_to_char(billable)}",
        )
    )
    return {
        "tenant_id": tenant_id,
        "period_start": start_day,
        "period_end": end_day,
        "used_units": used,
        "quota_units": included,
        "rollover_units": rollover,
        "billable_units": billable,
        "first_tier_units": first_tier,
        "second_tier_units": second_tier,
        "overage_amount": overage,
        "subscription_id": subscription.get("_id"),
    }


def _rating_row(rating):
    return _row(
        [
            (name, rating[name])
            for name in (
                "tenant_id",
                "period_start",
                "period_end",
                "used_units",
                "quota_units",
                "rollover_units",
                "billable_units",
                "first_tier_units",
                "second_tier_units",
                "overage_amount",
            )
        ]
    )


def usage_rating(tenant, start, end):
    audit = []
    try:
        rating = _compute_rating(tenant, start, end, audit)
    finally:
        _write_audit(audit)
    return [_rating_row(rating)]


def usage_summary(tenant, start, end):
    groups = {}
    for event in db.usage_events.find(
        {"tenant_id": tenant, "occurred_at": _period_window(start, end)},
        {"units": 1, "kind_cd": 1},
    ):
        kind = _USAGE_KIND.get(event.get("kind_cd"), "UNKNOWN")
        count, units = groups.get(kind, (0, Decimal(0)))
        groups[kind] = (count + 1, units + (_dec(event.get("units")) or 0))
    return [
        _row([("kind", kind), ("event_count", count), ("units", units)])
        for kind, (count, units) in sorted(groups.items())
    ]


def _finalize(session, audit, tenant_id, start, end):
    start_day, end_day = _day(start), _day(end)
    period_id = _md5_uuid(f"{tenant_id}{start_day:%Y-%m-%d}")
    existing = db.rating_periods.find_one(
        {"$or": [{"_id": period_id}, {"tenant_id": tenant_id, "period_start": start_day}]},
        {"_id": 1},
        session=session,
    )
    if existing:
        db.rating_periods.update_many(
            {"tenant_id": tenant_id, "period_start": start_day},
            {"$set": {"period_end": end_day}},
            session=session,
        )
    else:
        if not db.tenants.find_one({"_id": tenant_id}, {"_id": 1}, session=session):
            raise BackendError("tenant not found (FK_RP_TENANT)")
        db.rating_periods.insert_one(
            {
                "_id": period_id,
                "tenant_id": tenant_id,
                "period_start": start_day,
                "period_end": end_day,
            },
            session=session,
        )

    rating = _compute_rating(tenant_id, start_day, end_day, audit, session)
    quota, used = rating["quota_units"], rating["used_units"]
    rollover = None if quota is None else max(quota - used, Decimal(0))
    values = {
        "used_units": used,
        "rollover_units": rollover,
        "billable_units": rating["billable_units"],
        "overage_amount": rating["overage_amount"],
    }
    if any(value is None for value in values.values()):
        raise BackendError("cannot insert NULL into RATING_RESULTS (ORA-01400)")
    result_id = _md5_uuid(period_id)
    stored = {
        "used_units": Int64(int(used)),
        "rollover_units": Int64(int(rollover)),
        "billable_units": Int64(int(rating["billable_units"])),
        "overage_amount": _d128(rating["overage_amount"]),
    }
    if db.rating_results.find_one({"_id": result_id}, {"_id": 1}, session=session):
        db.rating_results.update_one({"_id": result_id}, {"$set": stored}, session=session)
    else:
        if rating["subscription_id"] is None or quota is None:
            raise BackendError("cannot insert NULL into RATING_RESULTS (ORA-01400)")
        db.rating_results.insert_one(
            {
                "_id": result_id,
                "period_id": period_id,
                "subscription_id": rating["subscription_id"],
                "quota_units": Int64(int(quota)),
                "created_at": end_day,
                **stored,
            },
            session=session,
        )
    audit.append(("RATING", f"finalized period={period_id}"))
    return period_id


def finalize_rating(tenant, start, end):
    _transaction(lambda session, audit: _finalize(session, audit, tenant, start, end))


def _preview(tenant_id, start, end, audit, session=None):
    start_day, end_day = _day(start), _day(end)
    plan_code = plan_fee = None
    for subscription in db.subscriptions.find(
        {
            "tenant_id": tenant_id,
            "starts_on": {"$lte": end_day},
            "$or": [{"ends_on": None}, {"ends_on": {"$gte": start_day}}],
        },
        sort=[("starts_on", DESCENDING)],
        session=session,
    ):
        plan = _plan(subscription.get("plan_id"), session)
        if plan:
            plan_code, plan_fee = plan.get("code"), _dec(plan.get("monthly_fee"))
            break

    overage = _compute_rating(tenant_id, start_day, end_day, audit, session)["overage_amount"]

    credit = Decimal(0)
    for note in db.credit_notes.find(
        {"tenant_id": tenant_id}, {"remaining_amount": 1}, session=session
    ):
        remaining = _dec(note.get("remaining_amount"))
        if remaining is not None and remaining > 0:
            credit += remaining

    tenant = db.tenants.find_one({"_id": tenant_id}, {"tax_exempt_yn": 1}, session=session)
    exempt = (tenant or {}).get("tax_exempt_yn") or "N"
    with localcontext(_NUMBER):
        if exempt == "Y":
            tax = Decimal(0)
        elif plan_fee is None or overage is None:
            tax = None
        else:
            tax = (plan_fee + overage) * TAX_RATE
        charge_cap = (
            None
            if plan_fee is None or overage is None or tax is None
            else _round(plan_fee + overage + tax, 2)
        )
        credit_applied = min(credit, charge_cap if charge_cap is not None else credit)
        half_tax = None if tax is None else tax / 2
    zero = Decimal(0)
    return [
        (1, "plan", plan_code, _round(plan_fee, 2), zero, zero, _round(plan_fee, 2)),
        (2, "usage", "usage overage", _round(overage, 2), zero, zero, _round(overage, 2)),
        (3, "tax", "regional tax", half_tax, zero, zero, half_tax),
        (4, "tax", "local tax", half_tax, zero, zero, half_tax),
        (5, "credit", "credit notes", zero, zero, credit_applied, -credit_applied),
    ]


_PREVIEW_COLUMNS = (
    "line_no", "line_type", "description", "amount", "tax_amount", "credit_applied", "total",
)


def invoice_preview(tenant, start, end):
    audit = []
    try:
        lines = _preview(tenant, start, end, audit)
    finally:
        _write_audit(audit)
    return [_row(zip(_PREVIEW_COLUMNS, line)) for line in lines]


def issue_invoice(tenant, start, end):
    start_day, end_day = _day(start), _day(end)

    def work(session, audit):
        period_id = _md5_uuid(f"{tenant}{start_day:%Y-%m-%d}")
        invoice_id = _md5_uuid(f"{period_id}invoice")
        _finalize(session, audit, tenant, start_day, end_day)
        lines = []
        subtotal = tax = credit = Decimal(0)
        for line_no, line_type, description, amount, _tax, applied, total in _preview(
            tenant, start_day, end_day, audit, session
        ):
            stored_amount = total if line_type == "credit" else amount
            if description is None or stored_amount is None:
                raise BackendError("cannot insert NULL into INVOICE_LINES (ORA-01400)")
            lines.append(
                {
                    "id": _md5_uuid(f"{invoice_id}{line_no}"),
                    "line_no": line_no,
                    "line_type": line_type,
                    "description": description,
                    "amount": _d128(_round(stored_amount, 2)),
                }
            )
            if line_type in ("plan", "usage"):
                subtotal += _round(amount, 2)
            elif line_type == "tax":
                tax += _round(amount, 2)
            elif line_type == "credit":
                credit = applied
        total = _round(subtotal + tax - credit, 2)
        header = {
            "subtotal": _d128(_round(subtotal, 2)),
            "tax": _d128(_round(tax, 2)),
            "total": _d128(total),
            "lines": lines,
        }
        if db.billing_invoices.find_one({"_id": invoice_id}, {"_id": 1}, session=session):
            db.billing_invoices.update_one(
                {"_id": invoice_id}, {"$set": {"status_cd": 20, **header}}, session=session
            )
        else:
            db.billing_invoices.insert_one(
                {
                    "_id": invoice_id,
                    "tenant_id": tenant,
                    "period_id": period_id,
                    "issued_at": end_day,
                    "status_cd": 20,
                    **header,
                },
                session=session,
            )

        notes = [
            note
            for note in db.credit_notes.find(
                {"tenant_id": tenant},
                sort=[("issued_on", ASCENDING), ("_id", ASCENDING)],
                session=session,
            )
            if (_dec(note.get("remaining_amount")) or 0) > 0
        ]
        for note in notes:
            if credit <= 0:
                break
            remaining = _dec(note["remaining_amount"])
            db.credit_notes.update_one(
                {"_id": note["_id"]},
                {"$set": {"remaining_amount": _d128(max(remaining - credit, Decimal(0)))}},
                session=session,
            )
            credit = max(credit - remaining, Decimal(0))
        audit.append(("INVOICING", f"issued invoice={invoice_id} total={_to_char(total)}"))

    _transaction(work)


def invoice_lines(invoice_id):
    invoice = db.billing_invoices.find_one({"_id": invoice_id}, {"lines": 1}) or {}
    lines = sorted(invoice.get("lines") or [], key=lambda line: line.get("line_no"))
    return [
        _row(
            [
                ("line_no", line.get("line_no")),
                ("line_type", line.get("line_type")),
                ("description", line.get("description")),
                ("amount", line.get("amount")),
            ]
        )
        for line in lines
    ]


def _overdue_invoices(session=None):
    return list(
        db.billing_invoices.find(
            {"status_cd": 40},
            {"lines": 0},
            sort=[("issued_at", ASCENDING), ("_id", ASCENDING)],
            session=session,
        )
    )


def overdue(as_of):
    as_of_day = _day(as_of)
    tenants = {}
    result = []
    for invoice in _overdue_invoices():
        issued = invoice["issued_at"]
        if _day(issued) >= as_of_day:
            continue
        tenant_id = invoice.get("tenant_id")
        if tenant_id not in tenants:
            tenants[tenant_id] = db.tenants.find_one({"_id": tenant_id}, {"status_cd": 1})
        tenant = tenants[tenant_id] or {}
        result.append(
            _row(
                [
                    ("tenant_id", tenant_id),
                    ("invoice_id", invoice["_id"]),
                    ("total", invoice.get("total")),
                    ("days_overdue", (as_of_day - _day(issued)).days),
                    ("tenant_status", _TENANT_STATUS.get(tenant.get("status_cd"), "UNKNOWN")),
                ]
            )
        )
    return result


def schedule_dunning(as_of):
    as_of_day = _day(as_of)
    weekday = as_of_day.weekday()
    scheduled_for = as_of_day + timedelta(days={5: 2, 6: 1}.get(weekday, 0))

    def work(session, audit):
        scheduled = 0
        for invoice in _overdue_invoices(session):
            last = db.dunning_attempts.find_one(
                {"invoice_id": invoice["_id"]},
                {"attempt_no": 1},
                sort=[("attempt_no", DESCENDING)],
                session=session,
            )
            attempt = (last["attempt_no"] if last else 0) + 1
            attempt_id = _md5_uuid(f"{invoice['_id']}{attempt}")
            clash = db.dunning_attempts.find_one(
                {"$or": [{"_id": attempt_id}, {"invoice_id": invoice["_id"], "attempt_no": attempt}]},
                {"_id": 1},
                session=session,
            )
            tenant = db.tenants.find_one({"_id": invoice.get("tenant_id")}, {"_id": 1}, session=session)
            if clash or not tenant:
                continue
            db.dunning_attempts.insert_one(
                {
                    "_id": attempt_id,
                    "tenant_id": invoice["tenant_id"],
                    "invoice_id": invoice["_id"],
                    "attempt_no": attempt,
                    "scheduled_for": scheduled_for,
                    "status_cd": 10,
                },
                session=session,
            )
            scheduled += 1
        audit.append(
            ("DUNNING", f"scheduled {scheduled} attempts as of {_dd_mon_yy(as_of_day)}")
        )

    _transaction(work)


def suspend_overdue(as_of):
    as_of_day = _day(as_of)
    cutoff = as_of_day - timedelta(days=14)
    _prime_sequence("seq_subscriptions_hist", "subscriptions_hist")

    def work(session, audit):
        tenant_ids = sorted(
            {
                invoice.get("tenant_id")
                for invoice in _overdue_invoices(session)
                if _day(invoice["issued_at"]) <= cutoff
            }
        )
        for tenant_id in tenant_ids:
            if not db.tenants.find_one({"_id": tenant_id, "status_cd": 10}, {"_id": 1}, session=session):
                continue
            db.tenants.update_one({"_id": tenant_id}, {"$set": {"status_cd": 20}}, session=session)
            for before in list(
                db.subscriptions.find({"tenant_id": tenant_id, "status_cd": 10}, session=session)
            ):
                _update_subscription(
                    session, before, {"status_cd": 20, "suspended_on": as_of_day}
                )
            notification_id = _md5_uuid(f"{tenant_id}suspension{as_of_day:%Y-%m-%d}")
            if not db.notifications.find_one(
                {
                    "$or": [
                        {"_id": notification_id},
                        {"tenant_id": tenant_id, "kind_cd": 3, "sent_at": as_of_day},
                    ]
                },
                {"_id": 1},
                session=session,
            ):
                db.notifications.insert_one(
                    {
                        "_id": notification_id,
                        "tenant_id": tenant_id,
                        "kind_cd": 3,
                        "sent_at": as_of_day,
                    },
                    session=session,
                )
            audit.append(("DUNNING", f"suspended tenant={tenant_id}"))

    _transaction(work)


def ensure_tenant(tenant_id, email):
    if db.tenants.find_one({"_id": tenant_id}, {"_id": 1}):
        return False
    name = email or tenant_id
    subscription_id = str(uuid5(NAMESPACE_URL, f"ow:{tenant_id}:sub"))

    def work(session, audit):
        if db.tenants.find_one(
            {"$or": [{"_id": tenant_id}, {"name": name}]}, {"_id": 1}, session=session
        ):
            return False
        plans = [
            plan
            for plan in db.plans.find({}, session=session)
            if plan.get("active_yn", "N") == "Y"
        ]
        if not plans:
            raise RuntimeError("no active Oracle billing plan")
        plan = min(plans, key=lambda item: (_dec(item["monthly_fee"]), item["_id"]))
        if db.subscriptions.find_one({"_id": subscription_id}, {"_id": 1}, session=session):
            return False
        db.tenants.insert_one(
            {"_id": tenant_id, "name": name, "tax_exempt_yn": "N", "status_cd": 10},
            session=session,
        )
        db.subscriptions.insert_one(
            {
                "_id": subscription_id,
                "tenant_id": tenant_id,
                "plan_id": plan["_id"],
                "starts_on": _day(_sysdate()),
                "status_cd": 10,
            },
            session=session,
        )
        return True

    try:
        return _transaction(work)
    except DuplicateKeyError:
        return False


provision_tenant = ensure_tenant


# --------------------------------------------------- facade read models


def tenant_profile(tenant_id):
    tenant = db.tenants.find_one({"_id": tenant_id})
    if not tenant:
        return []
    return [
        _row(
            [
                ("tenant_id", tenant["_id"]),
                ("name", tenant.get("name")),
                ("status", _code_desc("TENANT_STATUS", tenant.get("status_cd"))),
                ("tax_exempt", tenant.get("tax_exempt_yn")),
            ]
        )
    ]


def _first_customer(tenant_id, projection=None):
    return db.customers.find_one(
        {"tenant_id": tenant_id}, projection, sort=[("cust_seq_no", ASCENDING)]
    )


def customer_balance(tenant_id):
    columns = ("cust_no", "cust_name", "cur_bal_amt", "past_due_amt", "credit_hold_yn")
    customer = _first_customer(tenant_id, {name: 1 for name in columns})
    if not customer:
        return []
    return [_row([(name, customer.get(name)) for name in columns])]


def recent_usage_events(tenant_id, start, end):
    kinds = _codes("USAGE_KIND")
    result = []
    cursor = db.usage_events.find(
        {"tenant_id": tenant_id, "occurred_at": _period_window(start, end)},
        sort=[("occurred_at", DESCENDING), ("_id", DESCENDING)],
    )
    for event in cursor:
        if event.get("kind_cd") not in kinds:
            continue
        result.append(
            _row(
                [
                    ("id", event["_id"]),
                    ("occurred_at", event.get("occurred_at")),
                    ("units", event.get("units")),
                    ("kind", kinds[event["kind_cd"]]),
                ]
            )
        )
        if len(result) == 50:
            break
    return result


def tenant_invoices(tenant_id):
    statuses = _codes("INV_STATUS")
    result = []
    for invoice in db.billing_invoices.find(
        {"tenant_id": tenant_id},
        {"lines": 0},
        sort=[("issued_at", DESCENDING), ("_id", DESCENDING)],
    ):
        period = db.rating_periods.find_one({"_id": invoice.get("period_id")})
        if not period:
            continue
        result.append(
            _row(
                [
                    ("invoice_id", invoice["_id"]),
                    ("period_start", period.get("period_start")),
                    ("period_end", period.get("period_end")),
                    ("subtotal", invoice.get("subtotal")),
                    ("tax", invoice.get("tax")),
                    ("total", invoice.get("total")),
                    ("status", statuses.get(invoice.get("status_cd"))),
                ]
            )
        )
    return result


def invoice_owned(invoice_id, tenant_id):
    return db.billing_invoices.find_one({"_id": invoice_id, "tenant_id": tenant_id}, {"_id": 1}) is not None


def customer_detail(tenant_id):
    customer = _first_customer(tenant_id)
    if not customer:
        return None
    body = _row(
        [
            (name, customer.get("_id") if name == "cust_id" else customer.get(name))
            for name in CUSTOMER_COLUMNS
        ]
    )
    body["attributes"] = customer_attributes(customer)
    return body


def customer_attributes(customer):
    attributes = sorted(customer.get("attributes") or [], key=lambda item: item["eav_id"])
    return [
        _row(
            [
                (name, attribute.get(name))
                if name not in ("entity_type", "entity_id")
                else (name, "CUSTOMER" if name == "entity_type" else customer["_id"])
                for name in ATTRIBUTE_COLUMNS
            ]
        )
        for attribute in attributes
    ]


def dunning_schedule(as_of):
    statuses = _codes("DUN_STATUS")
    return [
        _row(
            [
                ("id", attempt["_id"]),
                ("tenant_id", attempt.get("tenant_id")),
                ("invoice_id", attempt.get("invoice_id")),
                ("attempt_no", attempt.get("attempt_no")),
                ("scheduled_for", attempt.get("scheduled_for")),
                ("status", statuses.get(attempt.get("status_cd"))),
            ]
        )
        for attempt in db.dunning_attempts.find(
            {"scheduled_for": {"$lte": _day(as_of)}},
            sort=[("scheduled_for", DESCENDING), ("_id", DESCENDING)],
            limit=200,
        )
    ]


def record_usage_event(tenant_id, email, event_id, occurred_at, units, kind):
    ensure_tenant(tenant_id, email)
    kind_doc = None
    if kind is not None:
        for code in db.codes.find({"code_type": "USAGE_KIND"}):
            if str(code.get("code_desc", "")).lower() == str(kind).lower():
                kind_doc = code
                break
    kind_cd = kind_doc["code_val"] if kind_doc else None
    if (units or 0) <= 0:
        raise UsageRejected("ORA-20001: units must be > 0")
    if kind_cd is None:
        raise UsageRejected("ORA-20002: unknown usage kind ")
    if not db.tenants.find_one({"_id": tenant_id}, {"_id": 1}):
        raise BackendError("tenant not found (FK_USAGE_TENANT)")
    occurred = _as_datetime(occurred_at)
    db.usage_events.insert_one(
        {
            "_id": event_id,
            "tenant_id": tenant_id,
            "occurred_at": occurred.replace(microsecond=0),
            "units": Int64(units),
            "kind_cd": kind_cd,
        }
    )


def usage_error_kind(exc):
    if isinstance(exc, DuplicateKeyError):
        return "duplicate"
    if isinstance(exc, UsageRejected):
        return "rejected"
    return None


# ----------------------------------------------------------- reports


def _invoice_status_label(statuses, status_cd):
    desc = statuses.get(status_cd)
    return desc if desc is not None else f"UNKNOWN({'' if status_cd is None else _to_char(status_cd)})"


def _present(path):
    return {"$cond": [{"$in": [{"$type": path}, ["missing", "null"]]}, 0, 1]}


def _sum_or_null(total, present):
    return total if present else None


def report_status_rows(batch_no):
    statuses = _codes("INV_STATUS")
    merged = {}
    for group in db.invoices.aggregate(
        [
            {"$match": {"batch_no": batch_no}},
            {
                "$group": {
                    "_id": "$status_cd",
                    "count": {"$sum": 1},
                    "total": {"$sum": "$total_amt"},
                    "present": {"$sum": _present("$total_amt")},
                }
            },
        ]
    ):
        label = _invoice_status_label(statuses, group["_id"])
        count, total, present = merged.get(label, (0, Decimal(0), 0))
        merged[label] = (
            count + group["count"],
            total + _dec(group["total"]),
            present + group["present"],
        )
    return [
        (label, Decimal(count), _fm_money(_sum_or_null(total, present)))
        for label, (count, total, present) in sorted(merged.items())
    ]


def report_line_rows(batch_no):
    statuses = _codes("INV_STATUS")
    merged = {}
    for group in db.invoices.aggregate(
        [
            {"$match": {"batch_no": batch_no}},
            {"$unwind": "$lines"},
            {
                "$group": {
                    "_id": {"status": "$status_cd", "type": "$lines.line_type_cd"},
                    "count": {"$sum": 1},
                    "amount": {"$sum": "$lines.amount"},
                    "amount_present": {
                        "$sum": _present("$lines.amount")
                    },
                    "tax": {"$sum": "$lines.tax_amt"},
                    "tax_present": {
                        "$sum": _present("$lines.tax_amt")
                    },
                    "invoices": {"$addToSet": "$_id"},
                }
            },
        ],
        allowDiskUse=True,
    ):
        status_cd, type_cd = group["_id"].get("status"), group["_id"].get("type")
        line_type = _LINE_TYPE.get(
            type_cd, f"UNKNOWN({'' if type_cd is None else _to_char(type_cd)})"
        )
        key = (_invoice_status_label(statuses, status_cd), line_type)
        count, amount, amount_n, tax, tax_n, invoices = merged.get(
            key, (0, Decimal(0), 0, Decimal(0), 0, set())
        )
        merged[key] = (
            count + group["count"],
            amount + _dec(group["amount"]),
            amount_n + group["amount_present"],
            tax + _dec(group["tax"]),
            tax_n + group["tax_present"],
            invoices | set(group["invoices"]),
        )
    return [
        (
            status,
            line_type,
            Decimal(count),
            _fm_money(_sum_or_null(amount, amount_n)),
            _fm_money(_sum_or_null(tax, tax_n)),
            Decimal(len(invoices)),
        )
        for (status, line_type), (count, amount, amount_n, tax, tax_n, invoices) in sorted(
            merged.items()
        )
    ]


def report_balances(batch_no):
    groups = list(
        db.customers.aggregate(
            [
                {"$match": {"conversion_batch_no": batch_no}},
                {
                    "$group": {
                        "_id": None,
                        "count": {"$sum": 1},
                        "cur": {"$sum": "$cur_bal_amt"},
                        "cur_present": {
                            "$sum": _present("$cur_bal_amt")
                        },
                        "past": {"$sum": "$past_due_amt"},
                        "past_present": {
                            "$sum": _present("$past_due_amt")
                        },
                    }
                },
            ]
        )
    )
    if not groups:
        return (Decimal(0), None, None)
    group = groups[0]
    return (
        Decimal(group["count"]),
        _fm_money(_sum_or_null(_dec(group["cur"]), group["cur_present"])),
        _fm_money(_sum_or_null(_dec(group["past"]), group["past_present"])),
    )


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
