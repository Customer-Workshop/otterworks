import os
import uuid
from datetime import date
from decimal import Decimal

import psycopg

NAME = "postgres"


def db_connect():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "billing_dev"),
        user=os.getenv("DB_USER", "billing"),
        password=os.getenv("DB_PASSWORD", "billing"),
    )


def json_value(value):
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
