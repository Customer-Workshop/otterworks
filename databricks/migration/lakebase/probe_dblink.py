#!/usr/bin/env python3
"""Can this Lakebase branch give log_msg a commit-independent writer?

Oracle's PRAGMA AUTONOMOUS_TRANSACTION commits the audit row even when the caller rolls back.
In Postgres that needs a second connection, which means the dblink extension. This probe asks
whether dblink is available to the migration role, so the answer is recorded rather than
assumed.
"""
import os

import psycopg


def main() -> int:
    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        raise SystemExit("OW_TP_LAKEBASE_DSN is not set; run under with_lakebase_dsn.py")
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT name, default_version, installed_version "
                    "FROM pg_available_extensions WHERE name IN ('dblink','postgres_fdw')")
        print("available:", cur.fetchall())
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS dblink")
            print("create dblink: ok")
        except Exception as exc:  # noqa: BLE001 - the failure text is the result
            print("create dblink: refused:", str(exc).strip().splitlines()[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
