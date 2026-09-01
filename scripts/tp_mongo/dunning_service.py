"""Application-side replacement for the Oracle PKG_DUNNING package."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from tp_mongo.rating_service import (
    NS_VALUE,
    TARGET_DB,
    _date_for_compare,
    _utc_ms,
    md5_uuid,
)
from tp_mongo.plans_service import history_doc

INVOICES = "invoices"
TENANTS = "tenants"
SUBSCRIPTIONS = "subscriptions"
SUBSCRIPTIONS_HIST = "subscriptions_hist"
NOTIFICATIONS = "notifications"
OVERDUE_STATUS_CD = 40
ACTIVE_STATUS_CD = 10
SUSPENDED_STATUS_CD = 20
ATTEMPT_SCHEDULED_STATUS_CD = 10
SUSPENSION_KIND_CD = 3
SUSPENSION_THRESHOLD_DAYS = 14
TENANT_STATUS_LABELS = {10: "active", 20: "suspended"}
UNKNOWN_TENANT_STATUS = "UNKNOWN"
# Port DECODE(TO_CHAR(day, 'DY'), 'SAT', 2, 'SUN', 1, 0) on Python weekday indexes.
WEEKEND_SHIFT_DAYS = {5: 2, 6: 1}
NS_FILTER = {"ns": NS_VALUE}


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    to_decimal = getattr(value, "to_decimal", None)
    if callable(to_decimal):
        value = to_decimal()
    return Decimal(str(value))


class DunningService:
    """Dunning operations restricted to the U6 target database."""

    def __init__(self, db, audit_sink: Callable | None = None):
        if db.name != TARGET_DB:
            raise ValueError(
                f"dunning service is restricted to {TARGET_DB}: got {db.name}"
            )
        self.db = db
        self.invoices = db[INVOICES]
        self.tenants = db[TENANTS]
        self.subscriptions = db[SUBSCRIPTIONS]
        # Port trg_subscriptions_hist's pre-image write for subscription updates.
        self.subscriptions_hist = db[SUBSCRIPTIONS_HIST]
        self.notifications = db[NOTIFICATIONS]
        self.audit_sink = audit_sink or (lambda _module, _message: None)
        self.last_run_dt: date | None = None
        self.scheduled_cnt = 0

    def _overdue_invoices(self, session=None) -> list[dict]:
        # Preserve the source cursor scope: status 40 only, ordered by issued_at, id.
        return list(
            self.invoices.find(
                {"status_cd": OVERDUE_STATUS_CD, **NS_FILTER}, session=session
            ).sort([("issued_at", 1), ("_id", 1)])
        )

    def overdue_accounts(self, as_of: date, session=None) -> list[dict]:
        # Preserve TO_CHAR(...,'YYYYMMDD') as a plain date-only comparison.
        as_of_day = _date_for_compare(as_of)
        rows = []
        for invoice in self._overdue_invoices(session=session):
            issued_on = _date_for_compare(invoice["issued_at"])
            if not issued_on < as_of_day:
                continue
            # Preserve the outer join: a missing tenant decodes to UNKNOWN.
            tenant = self.tenants.find_one(
                {"_id": invoice.get("tenant_id"), **NS_FILTER}, session=session
            )
            rows.append(
                {
                    "tenant_id": invoice.get("tenant_id"),
                    "invoice_id": invoice["_id"],
                    "total": _decimal(invoice.get("total")),
                    "days_overdue": (as_of_day - issued_on).days,
                    "tenant_status": TENANT_STATUS_LABELS.get(
                        (tenant or {}).get("status_cd"), UNKNOWN_TENANT_STATUS
                    ),
                }
            )
        return rows

    def _schedule_attempt(
        self, invoice: dict, attempt_no: int, scheduled_for: date
    ) -> bool:
        element = {
            "attempt_no": attempt_no,
            "id": md5_uuid(invoice["_id"] + str(attempt_no)),
            "tenant_id": invoice.get("tenant_id"),
            "scheduled_for": _utc_ms(scheduled_for),
            "status_cd": ATTEMPT_SCHEDULED_STATUS_CD,
        }
        try:
            result = self.invoices.update_one(
                {
                    "_id": invoice["_id"],
                    "ns": NS_VALUE,
                    "dunning_attempts.attempt_no": {"$ne": attempt_no},
                },
                {"$push": {"dunning_attempts": element}},
            )
            return result.modified_count == 1
        except Exception:  # noqa: BLE001
            # Port the source's WHEN OTHERS THEN NULL swallow.
            return False

    def schedule_dunning(self, as_of: date) -> dict:
        as_of_day = _date_for_compare(as_of)
        self.last_run_dt = as_of_day
        self.scheduled_cnt = 0
        scheduled_for = as_of_day + timedelta(
            days=WEEKEND_SHIFT_DAYS.get(as_of_day.weekday(), 0)
        )
        # Not transactional: the source swallows a failed insert and keeps going,
        # so an earlier attempt must survive a later failure.
        for invoice in self._overdue_invoices():
            attempts = invoice.get("dunning_attempts") or []
            attempt_no = (
                max((int(attempt["attempt_no"]) for attempt in attempts), default=0) + 1
            )
            if self._schedule_attempt(invoice, attempt_no, scheduled_for):
                self.scheduled_cnt += 1
        self.audit_sink(
            "DUNNING",
            f"scheduled {self.scheduled_cnt} attempts as of "
            f"{as_of_day.strftime('%d-%b-%y').upper()}",
        )
        return {"scheduled": self.scheduled_cnt, "last_run_dt": self.last_run_dt}

    def _suspension_candidates(self, as_of_day: date, session=None) -> list[str]:
        threshold = as_of_day - timedelta(days=SUSPENSION_THRESHOLD_DAYS)
        candidates = {
            invoice.get("tenant_id")
            for invoice in self._overdue_invoices(session=session)
            if _date_for_compare(invoice["issued_at"]) <= threshold
        }
        # The source SELECT DISTINCT is unordered; tenant_id order is a determinism choice.
        return sorted(candidates)

    def suspend_overdue(self, as_of: date) -> dict:
        as_of_day = _date_for_compare(as_of)
        suspended_on = _utc_ms(as_of_day)
        suspended: list[str] = []
        notifications_inserted = 0
        # The source procedure is a single transaction; keep that boundary.
        with self.db.client.start_session() as session, session.start_transaction():
            for tenant_id in self._suspension_candidates(as_of_day, session=session):
                active = self.tenants.count_documents(
                    {"_id": tenant_id, "status_cd": ACTIVE_STATUS_CD, **NS_FILTER},
                    session=session,
                )
                if not active:
                    continue
                self.tenants.update_one(
                    {"_id": tenant_id, **NS_FILTER},
                    {"$set": {"status_cd": SUSPENDED_STATUS_CD}},
                    session=session,
                )
                for subscription in self.subscriptions.find(
                    {
                        "tenant_id": tenant_id,
                        "status_cd": ACTIVE_STATUS_CD,
                        **NS_FILTER,
                    },
                    session=session,
                ):
                    self.subscriptions_hist.insert_one(
                        history_doc(subscription, "UPD"), session=session
                    )
                    self.subscriptions.update_one(
                        {"_id": subscription["_id"], **NS_FILTER},
                        {
                            "$set": {
                                "status_cd": SUSPENDED_STATUS_CD,
                                "suspended_on": suspended_on,
                            }
                        },
                        session=session,
                    )
                # Port the NOT EXISTS guard: an insert-if-absent upsert whose
                # uniqueness the (tenant_id, kind_cd, sent_at) index enforces.
                result = self.notifications.update_one(
                    {
                        "tenant_id": tenant_id,
                        "kind_cd": SUSPENSION_KIND_CD,
                        "sent_at": suspended_on,
                        "ns": NS_VALUE,
                    },
                    {
                        "$setOnInsert": {
                            "_id": md5_uuid(
                                tenant_id
                                + "suspension"
                                + as_of_day.strftime("%Y-%m-%d")
                            )
                        }
                    },
                    upsert=True,
                    session=session,
                )
                if result.upserted_id is not None:
                    notifications_inserted += 1
                suspended.append(tenant_id)
        for tenant_id in suspended:
            self.audit_sink("DUNNING", f"suspended tenant={tenant_id}")
        return {"suspended": suspended, "notifications_inserted": notifications_inserted}
