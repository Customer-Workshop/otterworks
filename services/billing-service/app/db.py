from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "001_initial.sql"
SEED = ROOT / "db" / "seed.sql"

TRUNCATE = """
TRUNCATE TABLE billing_svc.notifications,
               billing_svc.dunning_attempts,
               billing_svc.invoice_lines,
               billing_svc.invoices,
               billing_svc.credit_notes,
               billing_svc.rating_results,
               billing_svc.rating_periods,
               billing_svc.usage_events,
               billing_svc.subscriptions,
               billing_svc.plans,
               billing_svc.tenants
CASCADE
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def migrate() -> None:
    with connect() as connection:
        connection.execute(MIGRATION.read_text())


def reset() -> None:
    with connect() as connection:
        connection.execute(MIGRATION.read_text())
        connection.execute(TRUNCATE)
        connection.execute(SEED.read_text())
