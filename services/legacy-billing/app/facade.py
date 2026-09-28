import os
import re
from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request

from backends import get_backend
from backends import oracle  # noqa: F401  (tests patch facade_module.oracle.*)

facade = Blueprint("facade", __name__, url_prefix="/api/v1/billing")
internal = Blueprint("internal", __name__)

UNAVAILABLE = {
    "error": "legacy estate unavailable",
    "detail": "the billing estate is not reachable",
}
CANONICAL_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _backend():
    return get_backend()


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


def _ensure(tenant_id):
    _backend().ensure_tenant_by_id(tenant_id, request.headers.get("X-User-Email"))


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
    backend = _backend()
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
                for row in backend.list_plans()
            ]
        )
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/me")
def me():
    tenant_id, error = _identity()
    if error:
        return error
    backend = _backend()
    on, date_error = _parse_date(request.args.get("on"), "on")
    if date_error:
        return date_error
    try:
        _ensure(tenant_id)
        entitlement = backend.entitlement(tenant_id, on)
        body = backend.tenant_profile(tenant_id)
        if body is None:
            return jsonify(error="tenant not found"), 404
        body["entitlement"] = entitlement
        body["customer"] = backend.primary_customer(tenant_id)
        return jsonify(body)
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/entitlement")
def entitlement():
    tenant_id, error = _identity()
    if error:
        return error
    backend = _backend()
    on, date_error = _parse_date(request.args.get("on"), "on")
    if date_error:
        return date_error
    try:
        _ensure(tenant_id)
        return jsonify(backend.entitlement(tenant_id, on))
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.post("/plan-change")
def plan_change():
    tenant_id, error = _identity()
    if error:
        return error
    backend = _backend()
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
        if plan_id not in {row.get("plan_id") for row in backend.list_plans()}:
            return jsonify(error="invalid plan change", detail="plan_id is not a known billing plan"), 400
        _ensure(tenant_id)
        backend.change_plan(
            tenant_id,
            plan_id,
            effective_on,
        )
        return jsonify(
            status="changed",
            entitlement=backend.entitlement(
                tenant_id,
                effective_on,
            ),
        )
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/usage")
def usage():
    tenant_id, error = _identity()
    if error:
        return error
    backend = _backend()
    start, end, date_error = _usage_range()
    if date_error:
        return date_error
    try:
        _ensure(tenant_id)
        return jsonify(
            summary=backend.usage_summary(tenant_id, start, end),
            rating=backend.usage_rating(tenant_id, start, end),
            events=backend.usage_events(tenant_id, start, end),
        )
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/invoices")
def invoices():
    tenant_id, error = _identity()
    if error:
        return error
    backend = _backend()
    try:
        _ensure(tenant_id)
        return jsonify(backend.list_invoices(tenant_id))
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/invoices/<invoice_id>/lines")
def invoice_lines(invoice_id):
    tenant_id, error = _identity()
    if error:
        return error
    backend = _backend()
    try:
        _ensure(tenant_id)
        if not backend.invoice_owned(invoice_id, tenant_id):
            return jsonify(error="invoice not found"), 404
        return jsonify(backend.invoice_lines(invoice_id))
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/customer")
def customer():
    tenant_id, error = _identity()
    if error:
        return error
    backend = _backend()
    try:
        _ensure(tenant_id)
        body = backend.customer_with_attributes(tenant_id)
        if body is None:
            return jsonify(error="customer not found"), 404
        return jsonify(body)
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/admin/overdue")
def admin_overdue():
    if not _admin():
        return jsonify(error="forbidden"), 403
    backend = _backend()
    if not backend.SUPPORTS_DUNNING:
        return _not_available()
    as_of, date_error = _parse_date(request.args.get("as_of"), "as_of")
    if date_error:
        return date_error
    try:
        rows = backend.overdue(as_of)
        normalized = []
        for row in rows:
            row = dict(row)
            if "total" in row:
                row.setdefault("amount", row["total"])
            normalized.append(row)
        return jsonify(normalized)
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/admin/dunning")
def admin_dunning():
    if not _admin():
        return jsonify(error="forbidden"), 403
    backend = _backend()
    if not backend.SUPPORTS_DUNNING:
        return _not_available()
    as_of, date_error = _parse_date(request.args.get("as_of"), "as_of")
    if date_error:
        return date_error
    try:
        return jsonify(backend.dunning_attempts(as_of))
    except backend.Error:
        return jsonify(UNAVAILABLE), 503


@internal.post("/internal/usage/events")
def usage_event():
    expected_token = os.getenv("USAGE_INTERNAL_TOKEN")
    if not expected_token:
        return jsonify(error="internal usage ingest not configured"), 503
    if request.headers.get("X-Internal-Token") != expected_token:
        return jsonify(error="unauthorized"), 401
    backend = _backend()
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
    try:
        status = backend.record_usage_event(
            tenant_id,
            payload.get("email"),
            event_id,
            kind,
            units,
            occurred_at,
        )
        if status == "duplicate":
            return jsonify(status="duplicate")
        return jsonify(status="recorded"), 201
    except backend.ValidationError as exc:
        return jsonify(error=str(exc)), 422
    except backend.Error:
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
