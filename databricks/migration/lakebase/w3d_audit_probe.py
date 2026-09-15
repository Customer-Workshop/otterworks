"""Show the billing.billing_audit_log rows the converted pkg_dunning routines write.

Calls billing.sp_schedule_dunning and billing.sp_suspend_overdue on the wave branch inside a
single transaction, prints the audit rows the run produced, then ROLLBACKs. The rollback is
deliberate: the invoice state on the branch belongs to another unit and is still in flight,
and the dunning and notification tables carry this batch's reconciled rows, so the run must
observe them without changing them.

Usage:
  python3 databricks/migration/lakebase/with_lakebase_dsn.py OW_TP_LAKEBASE_DSN mig-p1-w2 -- \
  python3 databricks/migration/lakebase/w3d_audit_probe.py 2026-09-15
"""
import os
import sys

import psycopg


def main() -> int:
    as_of = sys.argv[1] if len(sys.argv) > 1 else "2026-09-15"
    conn = psycopg.connect(os.environ["OW_TP_LAKEBASE_DSN"])
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM billing.billing_audit_log")
            before = cur.fetchone()[0]

            cur.execute("CALL billing.sp_schedule_dunning(%s::timestamp(0))", (as_of,))
            cur.execute("CALL billing.sp_suspend_overdue(%s::timestamp(0))", (as_of,))

            cur.execute(
                "SELECT module, message FROM billing.billing_audit_log "
                "ORDER BY log_id OFFSET %s",
                (before,),
            )
            rows = cur.fetchall()
            print(f"as_of={as_of}  audit rows before={before}  written by this run={len(rows)}")
            for module, message in rows:
                print(f"  {module} | {message}")

            cur.execute("SELECT count(*) FROM billing.dunning_attempts")
            print("dunning_attempts in-transaction:", cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM billing.notifications")
            print("notifications in-transaction:", cur.fetchone()[0])
    finally:
        conn.rollback()
        conn.close()
    print("rolled back: no row on the wave branch changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
