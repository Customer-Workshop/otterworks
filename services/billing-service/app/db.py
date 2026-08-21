from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.config import settings

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "001_initial.sql"
SEED = ROOT / "db" / "seed.sql"


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def migrate() -> None:
    with connect() as connection:
        connection.execute(MIGRATION.read_text())


def reset() -> None:
    with connect() as connection:
        connection.execute(MIGRATION.read_text())
        tables = [
            row["table_name"]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                (settings.schema_name,),
            ).fetchall()
        ]
        if tables:
            targets = sql.SQL(", ").join(
                sql.Identifier(settings.schema_name, table) for table in tables
            )
            connection.execute(sql.SQL("TRUNCATE TABLE {} CASCADE").format(targets))
        connection.execute(SEED.read_text())
