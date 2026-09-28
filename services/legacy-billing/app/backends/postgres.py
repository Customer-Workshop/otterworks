import os
import uuid
from datetime import date, datetime, time
from decimal import Decimal

import psycopg

NAME = "postgres"
SUPPORTS_DUNNING = False
Error = psycopg.Error


class ValidationError(Exception):
    pass


def db_connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "billing_dev"),
        user=os.getenv("DB_USER", "billing"),
        password=os.getenv("DB_PASSWORD", "billing"),
    )


def json_value(value):
    if isinstance(value, datetime):
        if value.time() == time.min:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def rows(cursor):
    names = [column.name for column in cursor.description]
    return [{name: json_value(value) for name, value in zip(names, row)} for row in cursor]


def select(sql, params=()):
    with db_connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)
        return rows(cursor)


def execute(sql, params=()):
    with db_connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, params)


def health():
    select("SELECT 1")


def list_plans():
    return select("SELECT * FROM billing.fn_list_plans()")


def entitlement(tenant_id, on):
    return select(
        "SELECT * FROM billing.fn_entitlement(%s, %s)",
        (tenant_id, on),
    )


def change_plan(tenant_id, plan_id, effective_on):
    execute(
        "CALL billing.sp_change_plan(%s, %s, %s)",
        (tenant_id, plan_id, effective_on),
    )


def usage_rating(tenant, start, end):
    return select(
        "SELECT * FROM billing.fn_usage_rating(%s, %s, %s)",
        (tenant, start, end),
    )


def finalize_rating(tenant, start, end):
    execute(
        "CALL billing.sp_finalize_rating(%s, %s, %s)",
        (tenant, start, end),
    )


def invoice_preview(tenant, start, end):
    return select(
        "SELECT * FROM billing.fn_invoice_preview(%s, %s, %s)",
        (tenant, start, end),
    )


def issue_invoice(tenant, start, end):
    execute(
        "CALL billing.sp_issue_invoice(%s, %s, %s)",
        (tenant, start, end),
    )


def invoice_lines(invoice_id):
    return select("SELECT * FROM billing.fn_invoice_lines(%s)", (invoice_id,))


def overdue(as_of):
    return select(
        "SELECT * FROM billing.fn_overdue_accounts(%s)",
        (as_of,),
    )


def schedule_dunning(as_of):
    execute("CALL billing.sp_schedule_dunning(%s)", (as_of,))


def suspend_overdue(as_of):
    execute("CALL billing.sp_suspend_overdue(%s)", (as_of,))


def usage_summary(tenant, start, end):
    return select(
        "SELECT * FROM billing.fn_usage_summary(%s, %s, %s)",
        (tenant, start, end),
    )


def tenant_profile(tenant_id):
    rows_ = select(
        """SELECT t.id AS tenant_id, t.name,
                  ts.code_desc AS status, t.tax_exempt_yn AS tax_exempt
             FROM billing.tenants t
             LEFT JOIN billing.codes ts
               ON ts.code_type = 'TENANT_STATUS'
              AND ts.code_val = t.status_cd
            WHERE t.id = %s""",
        (tenant_id,),
    )
    return rows_[0] if rows_ else None


def primary_customer(tenant_id):
    return None


def usage_events(tenant_id, start, end, limit=50):
    return select(
        """SELECT u.id, u.occurred_at, u.units, c.code_desc AS kind
             FROM billing.usage_events u
             JOIN billing.codes c
               ON c.code_type = 'USAGE_KIND'
              AND c.code_val = u.kind_cd
            WHERE u.tenant_id = %s
              AND u.occurred_at >= %s::date
              AND u.occurred_at < %s::date + 1
            ORDER BY u.occurred_at DESC, u.id DESC
            LIMIT %s""",
        (tenant_id, start, end, limit),
    )


def list_invoices(tenant_id):
    return select(
        """SELECT i.id AS invoice_id, rp.period_start, rp.period_end,
                  i.subtotal, i.tax, i.total, c.code_desc AS status
             FROM billing.invoices i
             JOIN billing.rating_periods rp ON rp.id = i.period_id
             LEFT JOIN billing.codes c
               ON c.code_type = 'INV_STATUS'
              AND c.code_val = i.status_cd
            WHERE i.tenant_id = %s
            ORDER BY i.issued_at DESC, i.id DESC""",
        (tenant_id,),
    )


def invoice_owned(invoice_id, tenant_id):
    return bool(select(
        "SELECT 1 FROM billing.invoices WHERE id = %s AND tenant_id = %s",
        (invoice_id, tenant_id),
    ))


def customer_with_attributes(tenant_id):
    return None


def dunning_attempts(as_of, limit=200):
    raise NotImplementedError("dunning is not migrated")


def ensure_tenant_by_id(tenant_id, email):
    with db_connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM billing.tenants WHERE id = %s", (tenant_id,))
        if cursor.fetchone():
            return False
        cursor.execute(
            """INSERT INTO billing.tenants (id, name, tax_exempt_yn, status_cd)
               VALUES (%s, %s, 'N', 10)
               ON CONFLICT DO NOTHING""",
            (tenant_id, email or tenant_id),
        )
        cursor.execute(
            """SELECT id FROM billing.plans
               WHERE COALESCE(active_yn, 'N') = 'Y'
               ORDER BY monthly_fee, id
               LIMIT 1"""
        )
        plan = cursor.fetchone()
        if not plan:
            raise RuntimeError("no active billing plan")
        subscription_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ow:{tenant_id}:sub"))
        cursor.execute(
            """INSERT INTO billing.subscriptions
               (id, tenant_id, plan_id, starts_on, status_cd)
               VALUES (%s, %s, %s, CURRENT_DATE, 10)
               ON CONFLICT DO NOTHING""",
            (subscription_id, tenant_id, plan[0]),
        )
        return True


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def record_usage_event(tenant_id, email, event_id, kind, units, occurred_at):
    try:
        ensure_tenant_by_id(tenant_id, email)
        with db_connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT code_val FROM billing.codes
                    WHERE code_type = 'USAGE_KIND'
                      AND LOWER(code_desc) = LOWER(%s)""",
                (kind,),
            )
            kind_row = cursor.fetchone()
            cursor.execute(
                """INSERT INTO billing.usage_events
                   (id, tenant_id, occurred_at, units, kind_cd)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    event_id,
                    tenant_id,
                    _as_datetime(occurred_at),
                    units,
                    kind_row[0] if kind_row else None,
                ),
            )
        return "recorded"
    except psycopg.errors.UniqueViolation:
        return "duplicate"
    except psycopg.errors.RaiseException as exc:
        raise ValidationError(str(exc))
