"""Invoke one named legacy stored procedure on the reference warehouse."""

from __future__ import annotations

import argparse
import os
import re

import psycopg2
from psycopg2 import sql

DEFAULT_DSN = (
    "host=127.0.0.1 port=15432 dbname=analytics_dw "
    "user=dw_admin password=dw_local_dev sslmode=disable"
)
PROCEDURE_NAME = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--procedure", required=True)
    parser.add_argument("--dsn", default=os.environ.get("DW_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args(argv)
    if not PROCEDURE_NAME.fullmatch(args.procedure):
        parser.error("--procedure must be schema-qualified")
    schema, procedure = args.procedure.split(".", 1)
    with psycopg2.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                sql.SQL("CALL {}()").format(sql.Identifier(schema, procedure))
            )
    print(f"called {args.procedure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
