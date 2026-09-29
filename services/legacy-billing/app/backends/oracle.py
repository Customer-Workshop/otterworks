from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid5, NAMESPACE_URL

import oracledb

from oracle_conn import oracle_connect

NAME = "oracle"
ERRORS = (oracledb.Error,)


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


def provision_tenant(tenant_id, email):
    with oracle_connect() as connection:
        return ensure_tenant(connection, tenant_id, email)


def tenant_profile(tenant_id):
    return query(
        """SELECT t.id AS tenant_id, t.name,
                  ts.code_desc AS status, t.tax_exempt_yn AS tax_exempt
             FROM tenants t
             LEFT JOIN codes ts
               ON ts.code_type = 'TENANT_STATUS'
              AND ts.code_val = t.status_cd
            WHERE t.id = :1""",
        (tenant_id,),
    )


def customer_balance(tenant_id):
    return query(
        """SELECT cust_no, cust_name, cur_bal_amt, past_due_amt,
                  credit_hold_yn
             FROM customer_master
            WHERE tenant_id = :1
            ORDER BY cust_seq_no
            FETCH FIRST 1 ROWS ONLY""",
        (tenant_id,),
    )


def recent_usage_events(tenant_id, start, end):
    return query(
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
        (tenant_id, _as_date(start), end),
    )


def tenant_invoices(tenant_id):
    return query(
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


def invoice_owned(invoice_id, tenant_id):
    return bool(
        query(
            "SELECT 1 FROM invoices WHERE id = :1 AND tenant_id = :2",
            (invoice_id, tenant_id),
        )
    )


def customer_detail(tenant_id):
    customers = query(
        "SELECT * FROM customer_master WHERE tenant_id = :1 ORDER BY cust_seq_no FETCH FIRST 1 ROWS ONLY",
        (tenant_id,),
    )
    if not customers:
        return None
    body = customers[0]
    body["attributes"] = query(
        """SELECT * FROM entity_attr_value
            WHERE entity_type = 'CUSTOMER' AND entity_id = :1
            ORDER BY eav_id""",
        (customers[0]["cust_id"],),
    )
    return body


def dunning_schedule(as_of):
    return query(
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
        (_as_date(as_of),),
    )


def record_usage_event(tenant_id, email, event_id, occurred_at, units, kind):
    with oracle_connect() as connection:
        ensure_tenant(connection, tenant_id, email)
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT code_val FROM codes
                    WHERE code_type = 'USAGE_KIND'
                      AND LOWER(code_desc) = LOWER(:1)""",
                (kind,),
            )
            kind_row = cursor.fetchone()
            cursor.execute(
                """INSERT INTO usage_events
                   (id, tenant_id, occurred_at, units, kind_cd)
                   VALUES (:1, :2, :3, :4, :5)""",
                (
                    event_id,
                    tenant_id,
                    _as_datetime(occurred_at),
                    units,
                    kind_row[0] if kind_row else None,
                ),
            )
        connection.commit()


def usage_error_kind(exc):
    text = str(exc)
    if "ORA-00001" in text:
        return "duplicate"
    if "ORA-2000" in text:
        return "rejected"
    return None


def _as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
