from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid5, NAMESPACE_URL

import oracledb

from oracle_conn import oracle_connect

NAME = "oracle"


def _json_value(value):
    if isinstance(value, datetime):
        if value.time() == time.min:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def rows(cursor):
    names = [column[0].lower() for column in cursor.description]
    return [
        {name: _json_value(value) for name, value in zip(names, row)}
        for row in cursor
    ]


def query(sql, params=()):
    with oracle_connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return rows(cursor)


def _function(name, args=()):
    with oracle_connect() as connection, connection.cursor() as cursor:
        result = cursor.callfunc(name, oracledb.CURSOR, list(args))
        return rows(result)


def _procedure(name, args=()):
    with oracle_connect() as connection, connection.cursor() as cursor:
        cursor.callproc(name, list(args))
        connection.commit()


def health():
    query("SELECT 1 FROM DUAL")


def list_plans():
    return _function("pkg_plans.fn_list_plans")


def entitlement(tenant_id, on):
    return _function("pkg_plans.fn_entitlement", (tenant_id, _as_date(on)))


def change_plan(tenant_id, plan_id, effective_on):
    effective_date = _as_date(effective_on)
    with oracle_connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE subscriptions
               SET ends_on = :eff - 1,
                   status_cd = DECODE(status_cd, 30, 30, 10)
             WHERE tenant_id = :t
               AND ends_on IS NULL
               AND starts_on = :eff""",
            {"eff": effective_date, "t": tenant_id},
        )
        cursor.callproc(
            "pkg_plans.sp_change_plan",
            [tenant_id, plan_id, effective_date],
        )
        connection.commit()


def usage_rating(tenant, start, end):
    return _function(
        "pkg_rating.fn_usage_rating",
        (tenant, _as_date(start), _as_date(end)),
    )


def usage_summary(tenant, start, end):
    return _function(
        "pkg_rating.fn_usage_summary",
        (tenant, _as_date(start), _as_date(end)),
    )


def finalize_rating(tenant, start, end):
    _procedure(
        "pkg_rating.sp_finalize_rating",
        (tenant, _as_date(start), _as_date(end)),
    )


def invoice_preview(tenant, start, end):
    return _function(
        "pkg_invoicing.fn_invoice_preview",
        (tenant, _as_date(start), _as_date(end)),
    )


def issue_invoice(tenant, start, end):
    _procedure(
        "pkg_invoicing.sp_issue_invoice",
        (tenant, _as_date(start), _as_date(end)),
    )


def invoice_lines(invoice_id):
    return _function("pkg_invoicing.fn_invoice_lines", (invoice_id,))


def overdue(as_of):
    return _function("pkg_dunning.fn_overdue_accounts", (_as_date(as_of),))


def schedule_dunning(as_of):
    _procedure("pkg_dunning.sp_schedule_dunning", (_as_date(as_of),))


def suspend_overdue(as_of):
    _procedure("pkg_dunning.sp_suspend_overdue", (_as_date(as_of),))


def ensure_tenant(connection, tenant_id, email):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM tenants WHERE id = :1", (tenant_id,))
        if cursor.fetchone():
            return False
        try:
            cursor.execute(
                """INSERT INTO tenants (id, name, tax_exempt_yn, status_cd)
                   VALUES (:1, :2, 'N', 10)""",
                (tenant_id, email or tenant_id),
            )
        except oracledb.IntegrityError:
            connection.rollback()
            return False
        cursor.execute(
            """SELECT id FROM (
                   SELECT id FROM plans
                   WHERE NVL(active_yn, 'N') = 'Y'
                   ORDER BY monthly_fee, id
               ) WHERE ROWNUM = 1"""
        )
        plan = cursor.fetchone()
        if not plan:
            raise RuntimeError("no active Oracle billing plan")
        subscription_id = str(uuid5(NAMESPACE_URL, f"ow:{tenant_id}:sub"))
        try:
            cursor.execute(
                """INSERT INTO subscriptions
                   (id, tenant_id, plan_id, starts_on, status_cd)
                   VALUES (:1, :2, :3, TRUNC(SYSDATE), 10)""",
                (subscription_id, tenant_id, plan[0]),
            )
        except oracledb.IntegrityError:
            connection.rollback()
            return False
        connection.commit()
        return True


def _as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
