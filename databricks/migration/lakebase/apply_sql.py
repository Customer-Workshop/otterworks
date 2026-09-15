#!/usr/bin/env python3
"""Apply a .sql file to the Lakebase branch named by $OW_TP_LAKEBASE_DSN.

usage: python3 apply_sql.py <file.sql> [<file.sql> ...]
The DSN comes from the environment and is never printed.
"""
import os
import sys

import psycopg


def main(paths: list[str]) -> int:
    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        raise SystemExit("OW_TP_LAKEBASE_DSN is not set; run under with_lakebase_dsn.py")
    with psycopg.connect(dsn, autocommit=False) as conn:
        for path in paths:
            sql = open(path).read()
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"applied {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
