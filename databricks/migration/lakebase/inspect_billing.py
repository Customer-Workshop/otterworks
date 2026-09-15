#!/usr/bin/env python3
"""Read-only inventory of the billing schema on the Lakebase branch in $OW_TP_LAKEBASE_DSN.

Conversion work has to know which objects an earlier wave already merged onto the branch
(billing.plans, billing.f_md5_uuid, ...) before it writes SQL that depends on them. This
script only reads catalog metadata; it never writes, and it never prints the DSN.
"""
import os
import sys

import psycopg

TABLES = """
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'billing' ORDER BY 1
"""
ROUTINES = """
SELECT routine_name, routine_type FROM information_schema.routines
 WHERE routine_schema = 'billing' ORDER BY 1
"""
TRIGGERS = """
SELECT trigger_name, event_object_table, action_timing, event_manipulation
  FROM information_schema.triggers WHERE trigger_schema = 'billing' ORDER BY 1
"""


def main() -> int:
    dsn = os.environ.get("OW_TP_LAKEBASE_DSN")
    if not dsn:
        raise SystemExit("OW_TP_LAKEBASE_DSN is not set; run under with_lakebase_dsn.py")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for label, sql in (("tables", TABLES), ("routines", ROUTINES),
                           ("triggers", TRIGGERS)):
            cur.execute(sql)
            print(f"-- {label}")
            for row in cur.fetchall():
                print("  " + " | ".join(str(c) for c in row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
