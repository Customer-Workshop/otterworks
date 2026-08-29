"""Execute one legacy ELT SQL asset and assert its output cardinality."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "dw/legacy-estate/ddl/compat"))
from redshift_to_postgres import translate  # noqa: E402

DEFAULT_DSN = (
    "host=127.0.0.1 port=15432 dbname=analytics_dw "
    "user=dw_admin password=dw_local_dev sslmode=disable"
)
TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--expect-count", type=int)
    parser.add_argument("--dsn", default=os.environ.get("DW_POSTGRES_DSN", DEFAULT_DSN))
    args = parser.parse_args()
    if not TABLE_NAME.fullmatch(args.table):
        parser.error("--table must be schema-qualified")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    translated, rewrites = translate(args.script.read_text(), args.script)
    logging.info("running %s (%s)", args.script, rewrites)
    with psycopg2.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(translated)
            cursor.execute(f"SELECT COUNT(*) FROM {args.table}")
            count = cursor.fetchone()[0]
    logging.info("%s row_count=%s", args.table, count)
    if args.expect_count is not None and count != args.expect_count:
        raise SystemExit(
            f"{args.table}: expected {args.expect_count} rows, got {count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
