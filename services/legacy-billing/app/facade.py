from datetime import date

import oracledb
from flask import Blueprint, jsonify, request

from backends import backend_name
from backends import oracle

facade = Blueprint("facade", __name__, url_prefix="/api/v1/billing")
internal = Blueprint("internal", __name__)

UNAVAILABLE = {
    "error": "legacy estate unavailable",
    "detail": "the Oracle billing estate is not reachable",
}


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
    with oracle.oracle_connect() as connection:
        oracle.ensure_tenant(
            connection,
            tenant_id,
            request.headers.get("X-User-Email"),
        )


def _oracle_only():
    return backend_name() == "oracle"


@facade.get("/plans")
def plans():
    if not _oracle_only():
        return _not_available()
    try:
        return jsonify(
            [
                {
                    "plan_id": row.get("plan_id"),
                    "plan_code": row.get("code", row.get("plan_code")),
                    "tier": row.get("tier", row.get("code", row.get("plan_code"))),
                    "monthly_fee": row.get("monthly_fee"),
                    "included_units": row.get("included_units"),
                    "overage_rate": row.get("overage_rate"),
                }
                for row in oracle.list_plans()
            ]
        )
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/me")
def me():
    tenant_id, error = _identity()
    if error:
        return error
    if not _oracle_only():
        return _not_available()
    try:
        _ensure(tenant_id)
        on = request.args.get("on", date.today().isoformat())
        entitlement = oracle.entitlement(tenant_id, on)
        tenant_rows = oracle.query(
            """SELECT t.id AS tenant_id, t.name,
                      ts.code_desc AS status, t.tax_exempt_yn AS tax_exempt
                 FROM tenants t
                 LEFT JOIN codes ts
                   ON ts.code_type = 'TENANT_STATUS'
                  AND ts.code_val = t.status_cd
                WHERE t.id = :1""",
            (tenant_id,),
        )
        customer = oracle.query(
            """SELECT cust_no, cust_name, cur_bal_amt, past_due_amt,
                      credit_hold_yn
                 FROM customer_master
                WHERE tenant_id = :1
                ORDER BY cust_seq_no
                FETCH FIRST 1 ROWS ONLY""",
            (tenant_id,),
        )
        body = tenant_rows[0]
        body["entitlement"] = entitlement
        body["customer"] = customer[0] if customer else None
        return jsonify(body)
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/entitlement")
def entitlement():
    tenant_id, error = _identity()
    if error:
        return error
    if not _oracle_only():
        return _not_available()
    try:
        _ensure(tenant_id)
        return jsonify(
            oracle.entitlement(
                tenant_id,
                request.args.get("on", date.today().isoformat()),
            )
        )
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.post("/plan-change")
def plan_change():
    tenant_id, error = _identity()
    if error:
        return error
    if not _oracle_only():
        return _not_available()
    payload = request.get_json(force=True)
    try:
        _ensure(tenant_id)
        oracle.change_plan(
            tenant_id,
            payload["plan_id"],
            payload["effective_on"],
        )
        return jsonify(
            status="changed",
            entitlement=oracle.entitlement(
                tenant_id,
                payload["effective_on"],
            ),
        )
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/usage")
def usage():
    tenant_id, error = _identity()
    if error:
        return error
    if not _oracle_only():
        return _not_available()
    start, end = _usage_range()
    try:
        _ensure(tenant_id)
        return jsonify(
            summary=oracle.usage_summary(tenant_id, start, end),
            rating=oracle.usage_rating(tenant_id, start, end),
            events=oracle.query(
                """SELECT * FROM (
                       SELECT u.id, u.occurred_at, u.units, c.code_desc AS kind
                         FROM usage_events u
                         JOIN codes c
                           ON c.code_type = 'USAGE_KIND'
                          AND c.code_val = u.kind_cd
                        WHERE u.tenant_id = :1
                          AND u.occurred_at >= :2
                          AND u.occurred_at < TO_DATE(:3, 'YYYY-MM-DD') + 1
                        ORDER BY u.occurred_at DESC, u.id DESC
                   ) WHERE ROWNUM <= 50""",
                (tenant_id, oracle._as_date(start), end),
            ),
        )
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/invoices")
def invoices():
    tenant_id, error = _identity()
    if error:
        return error
    if not _oracle_only():
        return _not_available()
    try:
        _ensure(tenant_id)
        return jsonify(
            oracle.query(
                """SELECT i.id AS invoice_id, rp.period_start, rp.period_end,
                          i.subtotal, i.tax, i.total, c.code_desc AS status
                     FROM invoices i
                     JOIN rating_periods rp ON rp.id = i.period_id
                     LEFT JOIN codes c
                       ON c.code_type = 'INV_STATUS'
                      AND c.code_val = i.status_cd
                    WHERE i.tenant_id = :1
                    ORDER BY i.issued_at DESC, i.id DESC""",
                (tenant_id,),
            )
        )
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/invoices/<invoice_id>/lines")
def invoice_lines(invoice_id):
    tenant_id, error = _identity()
    if error:
        return error
    if not _oracle_only():
        return _not_available()
    try:
        _ensure(tenant_id)
        owned = oracle.query(
            "SELECT 1 FROM invoices WHERE id = :1 AND tenant_id = :2",
            (invoice_id, tenant_id),
        )
        if not owned:
            return jsonify(error="invoice not found"), 404
        return jsonify(oracle.invoice_lines(invoice_id))
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/customer")
def customer():
    tenant_id, error = _identity()
    if error:
        return error
    if not _oracle_only():
        return _not_available()
    try:
        _ensure(tenant_id)
        customers = oracle.query(
            "SELECT * FROM customer_master WHERE tenant_id = :1 ORDER BY cust_seq_no FETCH FIRST 1 ROWS ONLY",
            (tenant_id,),
        )
        if not customers:
            return jsonify(error="customer not found"), 404
        body = customers[0]
        body["attributes"] = oracle.query(
            """SELECT * FROM entity_attr_value
                WHERE entity_type = 'CUSTOMER' AND entity_id = :1
                ORDER BY eav_id""",
            (customers[0]["cust_id"],),
        )
        return jsonify(body)
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/admin/overdue")
def admin_overdue():
    if not _admin():
        return jsonify(error="forbidden"), 403
    if not _oracle_only():
        return _not_available()
    try:
        return jsonify(
            oracle.overdue(
                request.args.get("as_of", date.today().isoformat()),
            )
        )
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@facade.get("/admin/dunning")
def admin_dunning():
    if not _admin():
        return jsonify(error="forbidden"), 403
    if not _oracle_only():
        return _not_available()
    try:
        return jsonify(
            oracle.query(
                """SELECT * FROM (
                       SELECT d.id, d.tenant_id, d.invoice_id, d.attempt_no,
                              d.scheduled_for, c.code_desc AS status
                         FROM dunning_attempts d
                         LEFT JOIN codes c
                           ON c.code_type = 'DUN_STATUS'
                          AND c.code_val = d.status_cd
                        WHERE d.scheduled_for <= :1
                        ORDER BY d.scheduled_for DESC, d.id DESC
                   ) WHERE ROWNUM <= 200""",
                (oracle._as_date(request.args.get("as_of", date.today().isoformat())),),
            )
        )
    except oracledb.Error:
        return jsonify(UNAVAILABLE), 503


@internal.post("/internal/usage/events")
def usage_event():
    if not _oracle_only():
        return _not_available()
    payload = request.get_json(force=True)
    try:
        with oracle.oracle_connect() as connection:
            oracle.ensure_tenant(connection, payload["tenant_id"], payload.get("email"))
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT code_val FROM codes
                        WHERE code_type = 'USAGE_KIND'
                          AND LOWER(code_desc) = LOWER(:1)""",
                    (payload.get("kind"),),
                )
                kind_row = cursor.fetchone()
                cursor.execute(
                    """INSERT INTO usage_events
                       (id, tenant_id, occurred_at, units, kind_cd)
                       VALUES (:1, :2, :3, :4, :5)""",
                    (
                        payload["event_id"][:36],
                        payload["tenant_id"],
                        oracle._as_datetime(payload["occurred_at"]),
                        payload["units"],
                        kind_row[0] if kind_row else None,
                    ),
                )
            connection.commit()
        return jsonify(status="recorded"), 201
    except oracledb.Error as exc:
        text = str(exc)
        code = getattr(exc, "code", None)
        if code == 1 or "ORA-00001" in text:
            return jsonify(status="duplicate")
        if code in (20001, 20002) or "ORA-2000" in text:
            return jsonify(error=text), 422
        return jsonify(UNAVAILABLE), 503


def _usage_range():
    today = date.today()
    start = request.args.get("period_start")
    end = request.args.get("period_end")
    if not start:
        start = today.replace(day=1).isoformat()
    if not end:
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        end = next_month.fromordinal(next_month.toordinal() - 1).isoformat()
    return start, end
