"""Write a durable JSONL load audit without touching the dead warehouse asset."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2 import sql

DEFAULT_DSN = (
    "host=127.0.0.1 port=15432 dbname=analytics_dw "
    "user=dw_admin password=dw_local_dev sslmode=disable"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dsn", default=os.environ.get("DW_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args(argv)
    if args.table.count(".") != 1:
        parser.error("--table must be schema-qualified")
    schema, relation = args.table.split(".", 1)
    with psycopg2.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = %s
                """,
                (schema, relation),
            )
            if cursor.fetchone()[0] != 1:
                raise SystemExit(f"unknown table: {args.table}")
            cursor.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                sql.SQL("SELECT COUNT(*) FROM {}").format(
                    sql.Identifier(schema, relation)
                )
            )
            row_count = cursor.fetchone()[0]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "table": args.table,
        "row_count": row_count,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    with args.out.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
