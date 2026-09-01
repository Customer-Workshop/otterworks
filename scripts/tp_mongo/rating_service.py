"""MongoDB application-side replacement for the Oracle rating package."""
from __future__ import annotations

import calendar
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Callable, Iterable

from bson import Decimal128, Int64

NS_VALUE = "mongo_032752"
TARGET_DB = "ow_tp_mongodb_032752"
USAGE_EVENTS = "usage_events"
RATING_PERIODS = "rating_periods"
RATING_RESULTS = "rating_results"
CODES = "codes"
PLANS = "plans"
SUBSCRIPTIONS = "subscriptions"
TIER_BREAK = 101
SECOND_TIER_MULTIPLIER = Decimal("1.5")
SUSPENDED_STATUS_CD = 20
USAGE_KIND_LABELS = {1: "api", 2: "storage", 3: "compute"}


def md5_uuid(text: str) -> str:
    """Return the lower-case, hyphenated UUID-shaped MD5 used by f_md5_uuid."""
    # Port STANDARD_HASH(UTL_RAW.CAST_TO_RAW(text), 'MD5') formatting.
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"


def add_months(value: date, months: int) -> date:
    """Shift a date by months with Oracle ADD_MONTHS day semantics."""
    # Preserve ADD_MONTHS: a month-end input lands on the target month's last day,
    # every other day is clamped to the target month's length.
    month_index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    target_last_day = calendar.monthrange(year, month)[1]
    source_is_month_end = (
        value.day == calendar.monthrange(value.year, value.month)[1]
    )
    day = target_last_day if source_is_month_end else min(value.day, target_last_day)
    return value.replace(year=year, month=month, day=day)


class UsageEventRejected(Exception):
    """Raised when the Oracle usage-event trigger would reject an insert."""


@dataclass(frozen=True)
class Rating:
    tenant_id: str
    period_start: date
    period_end: date
    used_units: int
    quota_units: int | None
    rollover_units: int | None
    billable_units: int | None
    first_tier_units: int | None
    second_tier_units: int | None
    overage_amount: Decimal | None


def _midnight(value: date) -> datetime:
    return datetime(value.year, value.month, value.day)


def _utc_ms(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = _midnight(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    else:
        result = result.astimezone(timezone.utc)
    return result.replace(microsecond=(result.microsecond // 1000) * 1000)


def _date_for_compare(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def _decimal(value) -> Decimal:
    return Decimal(str(value))


def _round_decimal(value: Decimal, places: int) -> Decimal:
    # Oracle ROUND is half-away-from-zero, unlike Python's default rounding.
    quantum = Decimal(1).scaleb(-places)
    with localcontext() as context:
        context.prec = 38
        return value.quantize(quantum, rounding=ROUND_HALF_UP)


class MongoSubscriptionSource:
    """Read-only subscription lookup backed by the U3-owned collection."""

    def __init__(self, db):
        self.collection = db[SUBSCRIPTIONS]

    def latest_covering(
        self,
        tenant_id: str,
        period_start: date,
        period_end: date,
        session=None,
    ) -> dict | None:
        start = _midnight(_date_for_compare(period_start))
        end = _midnight(_date_for_compare(period_end))
        cursor = (
            self.collection.find(
                {
                    "tenant_id": tenant_id,
                    "starts_on": {"$lte": end},
                    "$or": [{"ends_on": None}, {"ends_on": {"$gte": start}}],
                },
                session=session,
            )
            .sort("starts_on", -1)
            .limit(1)
        )
        return next(iter(cursor), None)


class StaticSubscriptionSource:
    """In-memory implementation of the subscription lookup seam."""

    def __init__(self, rows: Iterable[dict]):
        self.rows = list(rows)

    def latest_covering(
        self,
        tenant_id: str,
        period_start: date,
        period_end: date,
        session=None,
    ) -> dict | None:
        start = _date_for_compare(period_start)
        end = _date_for_compare(period_end)
        matches = [
            row
            for row in self.rows
            if row.get("tenant_id") == tenant_id
            and _date_for_compare(row["starts_on"]) <= end
            and (
                row.get("ends_on") is None
                or _date_for_compare(row["ends_on"]) >= start
            )
        ]
        return max(matches, key=lambda row: _date_for_compare(row["starts_on"]), default=None)


class RatingService:
    """Rating operations restricted to the U4 target database and collections."""

    def __init__(
        self, db, subscription_source=None, audit_sink: Callable | None = None
    ):
        if db.name != TARGET_DB:
            raise ValueError(f"rating service is restricted to {TARGET_DB}: got {db.name}")
        self.db = db
        self.usage_events = db[USAGE_EVENTS]
        self.rating_periods = db[RATING_PERIODS]
        self.rating_results = db[RATING_RESULTS]
        self.codes = db[CODES]
        self.plans = db[PLANS]
        self.subscription_source = subscription_source or MongoSubscriptionSource(db)
        self.audit_sink = audit_sink or (lambda _module, _message: None)

    def window_bounds(
        self, period_start: date, period_end: date
    ) -> tuple[datetime, datetime]:
        # Replace the legacy TO_CHAR(...,'YYYYMMDD') window comparison at day granularity.
        return _midnight(_date_for_compare(period_start)), _midnight(
            _date_for_compare(period_end)
        ) + timedelta(days=1)

    def sum_usage_units(
        self,
        tenant_id: str,
        period_start: date,
        period_end: date,
        session=None,
    ) -> int:
        # Preserve the source cursor's NVL(r.units, 0) sum semantics.
        start, end = self.window_bounds(period_start, period_end)
        rows = self.usage_events.aggregate(
            [
                {
                    "$match": {
                        "tenant_id": tenant_id,
                        "occurred_at": {"$gte": start, "$lt": end},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "units": {"$sum": {"$ifNull": ["$units", 0]}},
                    }
                },
            ],
            session=session,
        )
        result = next(iter(rows), None)
        return int(result.get("units", 0)) if result else 0

    def usage_summary(
        self,
        tenant_id: str,
        period_start: date,
        period_end: date,
        session=None,
    ) -> list[dict]:
        # Replace DECODE(u.kind_cd, ...) with an aggregation $switch.
        start, end = self.window_bounds(period_start, period_end)
        rows = self.usage_events.aggregate(
            [
                {
                    "$match": {
                        "tenant_id": tenant_id,
                        "occurred_at": {"$gte": start, "$lt": end},
                    }
                },
                {
                    "$group": {
                        "_id": {
                            "$switch": {
                                "branches": [
                                    {"case": {"$eq": ["$kind_cd", code]}, "then": label}
                                    for code, label in USAGE_KIND_LABELS.items()
                                ],
                                "default": "UNKNOWN",
                            }
                        },
                        "event_count": {"$sum": 1},
                        "units": {"$sum": {"$ifNull": ["$units", 0]}},
                    }
                },
                {"$sort": {"_id": 1}},
            ],
            session=session,
        )
        return [
            {
                "kind": row["_id"],
                "event_count": int(row["event_count"]),
                "units": int(row["units"]),
            }
            for row in rows
        ]

    def prior_rollover_units(
        self, tenant_id: str, period_start: date, session=None
    ) -> int:
        # Preserve ADD_MONTHS(p_period_start, -3) for the prior-credit window.
        lower_bound = _midnight(
            add_months(_date_for_compare(period_start), -3)
        )
        period_start_bound = _midnight(_date_for_compare(period_start))
        rows = self.rating_results.aggregate(
            [
                {
                    "$lookup": {
                        "from": RATING_PERIODS,
                        "localField": "period_id",
                        "foreignField": "_id",
                        "as": "period",
                    }
                },
                {"$unwind": "$period"},
                {
                    "$match": {
                        "period.tenant_id": tenant_id,
                        "period.period_start": {
                            "$lt": period_start_bound,
                            "$gte": lower_bound,
                        },
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "rollover_units": {
                            "$sum": {"$ifNull": ["$rollover_units", 0]}
                        },
                    }
                },
            ],
            session=session,
        )
        result = next(iter(rows), None)
        return int(result.get("rollover_units", 0)) if result else 0

    def compute_rating(
        self,
        tenant_id: str,
        period_start: date,
        period_end: date,
        session=None,
    ) -> Rating:
        with localcontext() as context:
            context.prec = 38
            sub = self.subscription_source.latest_covering(
                tenant_id, period_start, period_end, session=session
            )
            plan = (
                self.plans.find_one({"_id": sub["plan_id"]}, session=session)
                if sub and sub.get("plan_id")
                else None
            )
            included = int(plan["included_units"]) if plan else None
            rate = _decimal(plan["overage_rate"]) if plan else None
            used = self.sum_usage_units(
                tenant_id, period_start, period_end, session=session
            )
            prior = self.prior_rollover_units(
                tenant_id, period_start, session=session
            )
            # Preserve the Oracle LEAST/NVL NULL behavior for a missing plan.
            prior = min(2 * included, prior) if included is not None else prior
            quota = included
            rollover = min(prior, included * 2) if included is not None else prior
            billable = max(used - rollover - included, 0) if included is not None else 0
            first = min(billable, TIER_BREAK)
            second = max(billable - TIER_BREAK, 0)
            overage = (
                None
                if rate is None
                else _round_decimal(
                    Decimal(first) * rate
                    + Decimal(second) * rate * SECOND_TIER_MULTIPLIER,
                    2,
                )
            )
            if (
                sub
                and sub.get("status_cd") == SUSPENDED_STATUS_CD
                and sub.get("suspended_on") is not None
                and _date_for_compare(period_start)
                <= _date_for_compare(sub["suspended_on"])
                <= _date_for_compare(period_end)
            ):
                suspended_on = _date_for_compare(sub["suspended_on"])
                total_days = (
                    _date_for_compare(period_end) - _date_for_compare(period_start)
                ).days + 1
                remaining_days = (
                    _date_for_compare(period_end) - suspended_on
                ).days + 1
                factor = Decimal(remaining_days) / Decimal(total_days)
                billable = int(_round_decimal(Decimal(billable) * factor, 0))
                overage = (
                    None
                    if overage is None
                    else _round_decimal(overage * factor, 2)
                )
            self.audit_sink(
                "RATING",
                f"compute tenant={tenant_id} used={used if used is not None else -1} "
                f"billable={billable if billable is not None else -1}",
            )
            return Rating(
                tenant_id=tenant_id,
                period_start=period_start,
                period_end=period_end,
                used_units=used,
                quota_units=quota,
                rollover_units=rollover,
                billable_units=billable,
                first_tier_units=first,
                second_tier_units=second,
                overage_amount=overage,
            )

    def finalize_rating(
        self,
        tenant_id: str,
        period_start: date,
        period_end: date,
        session=None,
    ) -> dict:
        if session is None:
            with self.db.client.start_session() as transaction_session:
                return transaction_session.with_transaction(
                    lambda callback_session: self._finalize_rating(
                        tenant_id, period_start, period_end, callback_session
                    )
                )
        return self._finalize_rating(tenant_id, period_start, period_end, session)

    def _finalize_rating(
        self, tenant_id: str, period_start: date, period_end: date, session
    ) -> dict:
        period_id = md5_uuid(tenant_id + period_start.strftime("%Y-%m-%d"))
        period_start_dt = _midnight(_date_for_compare(period_start))
        period_end_dt = _midnight(_date_for_compare(period_end))
        sub = self.subscription_source.latest_covering(
            tenant_id, period_start, period_end, session=session
        )
        subscription_id = sub["_id"] if sub else None
        # Preserve the source insert-then-update upsert rather than replace semantics:
        # the insert keys on the period id while the fallback updates by
        # (tenant_id, period_start).
        existing_period = self.rating_periods.find_one(
            {"_id": period_id}, session=session
        )
        inserted_period = existing_period is None
        if inserted_period:
            self.rating_periods.insert_one(
                {
                    "_id": period_id,
                    "tenant_id": tenant_id,
                    "period_start": period_start_dt,
                    "period_end": period_end_dt,
                    "ns": NS_VALUE,
                },
                session=session,
            )
        else:
            self.rating_periods.update_many(
                {"tenant_id": tenant_id, "period_start": period_start_dt},
                {"$set": {"period_end": period_end_dt}},
                session=session,
            )

        rating = self.compute_rating(
            tenant_id, period_start, period_end, session=session
        )
        result_id = md5_uuid(period_id)
        # Preserve the source GREATEST(quota_units - used_units, 0) stored rollover.
        stored_rollover = (
            max(rating.quota_units - rating.used_units, 0)
            if rating.quota_units is not None
            else None
        )
        result_document = {
            "_id": result_id,
            "period_id": period_id,
            "subscription_id": subscription_id,
            "used_units": Int64(rating.used_units),
            "quota_units": (
                Int64(rating.quota_units) if rating.quota_units is not None else None
            ),
            "rollover_units": (
                Int64(stored_rollover) if stored_rollover is not None else None
            ),
            "billable_units": (
                Int64(rating.billable_units)
                if rating.billable_units is not None
                else None
            ),
            "overage_amount": (
                Decimal128(rating.overage_amount)
                if rating.overage_amount is not None
                else None
            ),
            "created_at": period_end_dt,
            "ns": NS_VALUE,
        }
        existing_result = self.rating_results.find_one(
            {"_id": result_id}, session=session
        )
        inserted_result = existing_result is None
        if inserted_result:
            self.rating_results.insert_one(result_document, session=session)
        else:
            self.rating_results.update_one(
                {"_id": result_id},
                {
                    "$set": {
                        "used_units": Int64(rating.used_units),
                        "rollover_units": (
                            Int64(stored_rollover)
                            if stored_rollover is not None
                            else None
                        ),
                        "billable_units": (
                            Int64(rating.billable_units)
                            if rating.billable_units is not None
                            else None
                        ),
                        "overage_amount": (
                            Decimal128(rating.overage_amount)
                            if rating.overage_amount is not None
                            else None
                        ),
                    }
                },
                session=session,
            )
        self.audit_sink("RATING", f"finalized period={period_id}")
        return {
            "period_id": period_id,
            "result_id": result_id,
            "rating": rating,
            "inserted_period": inserted_period,
            "inserted_result": inserted_result,
        }

    def insert_usage_event(self, event: dict) -> str:
        # Port trg_usage_events_check's NVL(units, 0) and CODES lookup checks.
        units = int(event.get("units") or 0)
        if units <= 0:
            raise UsageEventRejected("units must be > 0")
        kind_cd = int(event["kind_cd"])
        if (
            self.codes.count_documents(
                {"code_type": "USAGE_KIND", "code_val": kind_cd}
            )
            == 0
        ):
            raise UsageEventRejected(f"unknown usage kind {kind_cd}")
        document = dict(event)
        document["tenant_id"] = str(event["tenant_id"])
        document["occurred_at"] = _utc_ms(event["occurred_at"])
        document["units"] = Int64(units)
        document["kind_cd"] = kind_cd
        document["ns"] = NS_VALUE
        result = self.usage_events.insert_one(document)
        return str(result.inserted_id)
