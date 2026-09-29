import os
import re
from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request

from backends import backend_name, get_backend
from backends import oracle  # noqa: F401

facade = Blueprint("facade", __name__, url_prefix="/api/v1/billing")
internal = Blueprint("internal", __name__)

UNAVAILABLE = {
    "error": "legacy estate unavailable",
    "detail": "the Oracle billing estate is not reachable",
}
CANONICAL_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _not_available():
    return jsonify(error="not available on this backend"), 501


def _identity():
    tenant_id = request.headers.get("X-User-ID")
    if not tenant_id:
        return None, (jsonify(error="missing user identity"), 401)
    return tenant_id, None


def _admin():
    return "ADMIN" in {
        role.strip().upper()
        for role in request.headers.get("X-User-Roles", "").split(",")
        if role.strip()
    }


FACADE_BACKENDS = {"oracle", "mongo"}


def _readonly():
    return os.getenv("BILLING_READONLY", "").strip().lower() in {"1", "true", "yes"}


def _db():
    return get_backend()


def _ensure(tenant_id):
    if _readonly():
        return
    _db().provision_tenant(tenant_id, request.headers.get("X-User-Email"))


def _facade_backend():
    return backend_name() in FACADE_BACKENDS


def _parse_date(value, name):
    if value is None:
        value = date.today().isoformat()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None, (
            jsonify(
                error="invalid date",
                detail=f"{name} must be an ISO date (YYYY-MM-DD)",
            ),
            400,
        )
    return parsed.isoformat(), None


@facade.get("/plans")
def plans():
    _, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    try:
        return jsonify(
            [
                {
                    "plan_id": row.get("plan_id"),
                    "plan_code": row["code"],
                    "tier": row["tier"],
                    "monthly_fee": row.get("monthly_fee"),
                    "included_units": row.get("included_units"),
                    "overage_rate": row.get("overage_rate"),
                }
                for row in _db().list_plans()
            ]
        )
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/me")
def me():
    tenant_id, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    on, date_error = _parse_date(request.args.get("on"), "on")
    if date_error:
        return date_error
    try:
        _ensure(tenant_id)
        entitlement = _db().entitlement(tenant_id, on)
        tenant_rows = _db().tenant_profile(tenant_id)
        customer = _db().customer_balance(tenant_id)
        body = tenant_rows[0]
        body["entitlement"] = entitlement
        body["customer"] = customer[0] if customer else None
        return jsonify(body)
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/entitlement")
def entitlement():
    tenant_id, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    on, date_error = _parse_date(request.args.get("on"), "on")
    if date_error:
        return date_error
    try:
        _ensure(tenant_id)
        return jsonify(_db().entitlement(tenant_id, on))
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.post("/plan-change")
def plan_change():
    tenant_id, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="invalid plan change", detail="request body must be a JSON object"), 400
    plan_id = payload.get("plan_id")
    effective_on = payload.get("effective_on")
    if not isinstance(plan_id, str) or not plan_id.strip():
        return jsonify(error="invalid plan change", detail="plan_id must be a non-empty string"), 400
    if not isinstance(effective_on, str) or not effective_on.strip():
        return jsonify(error="invalid plan change", detail="effective_on must be a non-empty string"), 400
    try:
        effective_date = datetime.strptime(effective_on, "%Y-%m-%d").date()
    except ValueError:
        return jsonify(error="invalid plan change", detail="effective_on must be an ISO date (YYYY-MM-DD)"), 400
    if effective_date < datetime.now(timezone.utc).date():
        return jsonify(error="invalid plan change", detail="effective_on must be today or later"), 400
    try:
        if plan_id not in {row.get("plan_id") for row in _db().list_plans()}:
            return jsonify(error="invalid plan change", detail="plan_id is not a known billing plan"), 400
        _ensure(tenant_id)
        _db().change_plan(
            tenant_id,
            plan_id,
            effective_on,
        )
        return jsonify(
            status="changed",
            entitlement=_db().entitlement(
                tenant_id,
                effective_on,
            ),
        )
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/usage")
def usage():
    tenant_id, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    start, end, date_error = _usage_range()
    if date_error:
        return date_error
    try:
        _ensure(tenant_id)
        return jsonify(
            summary=_db().usage_summary(tenant_id, start, end),
            rating=_db().usage_rating(tenant_id, start, end),
            events=_db().recent_usage_events(tenant_id, start, end),
        )
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/invoices")
def invoices():
    tenant_id, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    try:
        _ensure(tenant_id)
        return jsonify(_db().tenant_invoices(tenant_id))
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/invoices/<invoice_id>/lines")
def invoice_lines(invoice_id):
    tenant_id, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    try:
        _ensure(tenant_id)
        if not _db().invoice_owned(invoice_id, tenant_id):
            return jsonify(error="invoice not found"), 404
        return jsonify(_db().invoice_lines(invoice_id))
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/customer")
def customer():
    tenant_id, error = _identity()
    if error:
        return error
    if not _facade_backend():
        return _not_available()
    try:
        _ensure(tenant_id)
        body = _db().customer_detail(tenant_id)
        if body is None:
            return jsonify(error="customer not found"), 404
        return jsonify(body)
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/admin/overdue")
def admin_overdue():
    if not _admin():
        return jsonify(error="forbidden"), 403
    if not _facade_backend():
        return _not_available()
    as_of, date_error = _parse_date(request.args.get("as_of"), "as_of")
    if date_error:
        return date_error
    try:
        rows = _db().overdue(as_of)
        normalized = []
        for row in rows:
            row = dict(row)
            if "total" in row:
                row.setdefault("amount", row["total"])
            normalized.append(row)
        return jsonify(normalized)
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@facade.get("/admin/dunning")
def admin_dunning():
    if not _admin():
        return jsonify(error="forbidden"), 403
    if not _facade_backend():
        return _not_available()
    as_of, date_error = _parse_date(request.args.get("as_of"), "as_of")
    if date_error:
        return date_error
    try:
        return jsonify(_db().dunning_schedule(as_of))
    except _db().ERRORS:
        return jsonify(UNAVAILABLE), 503


@internal.post("/internal/usage/events")
def usage_event():
    expected_token = os.getenv("USAGE_INTERNAL_TOKEN")
    if not expected_token:
        return jsonify(error="internal usage ingest not configured"), 503
    if request.headers.get("X-Internal-Token") != expected_token:
        return jsonify(error="unauthorized"), 401
    if not _facade_backend():
        return _not_available()
    raw_body = request.get_data(cache=True)
    if len(raw_body) > 16 * 1024:
        return jsonify(error="invalid usage event", detail="request body exceeds 16 KB"), 400
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="invalid usage event", detail="request body must be a JSON object"), 400
    tenant_id = payload.get("tenant_id")
    event_id = payload.get("event_id")
    kind = payload.get("kind")
    units = payload.get("units")
    occurred_at = payload.get("occurred_at")
    if not isinstance(tenant_id, str) or not tenant_id or len(tenant_id) > 64:
        return jsonify(error="invalid usage event", detail="tenant_id must be a string of at most 64 characters"), 400
    if not isinstance(event_id, str) or not CANONICAL_UUID.fullmatch(event_id):
        return jsonify(error="invalid usage event", detail="event_id must be a canonical UUID"), 400
    if kind not in {"api", "storage", "compute"}:
        return jsonify(error="invalid usage event", detail="kind must be api, storage, or compute"), 400
    if isinstance(units, bool) or not isinstance(units, int) or not 1 <= units <= 1_000_000:
        return jsonify(error="invalid usage event", detail="units must be an integer from 1 to 1000000"), 400
    if not isinstance(occurred_at, str):
        return jsonify(error="invalid usage event", detail="occurred_at must be an ISO-8601 timestamp"), 400
    try:
        datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError:
        return jsonify(error="invalid usage event", detail="occurred_at must be an ISO-8601 timestamp"), 400
    db = _db()
    try:
        db.record_usage_event(
            tenant_id,
            payload.get("email"),
            payload["event_id"],
            occurred_at,
            units,
            payload.get("kind"),
        )
        return jsonify(status="recorded"), 201
    except db.ERRORS as exc:
        outcome = db.usage_error_kind(exc)
        if outcome == "duplicate":
            return jsonify(status="duplicate")
        if outcome == "rejected":
            return jsonify(error=str(exc)), 422
        return jsonify(UNAVAILABLE), 503


def _usage_range():
    today = date.today()
    start = request.args.get("period_start")
    end = request.args.get("period_end")
    if start is None:
        start = today.replace(day=1).isoformat()
    if end is None:
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        end = next_month.fromordinal(next_month.toordinal() - 1).isoformat()
    start, error = _parse_date(start, "period_start")
    if error:
        return None, None, error
    end, error = _parse_date(end, "period_end")
    if error:
        return None, None, error
    if end < start:
        return None, None, (
            jsonify(
                error="invalid date",
                detail="period_end must not precede period_start",
            ),
            400,
        )
    return start, end, None
