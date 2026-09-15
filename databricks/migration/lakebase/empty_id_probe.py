"""Probe: an empty tenant/plan id must fail sp_assign_plan the way it fails on Oracle.

Runs inside a transaction that is always rolled back, so the target keeps the state the
loader put there.
"""

import os
import sys

import psycopg


def main() -> int:
    with psycopg.connect(os.environ["OW_TP_LAKEBASE_DSN"]) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "CALL billing.sp_assign_plan(%s, %s, %s)",
                    ("00000000-0000-0000-0000-000000000001", "", "2026-07-01"),
                )
            except psycopg.errors.NotNullViolation as exc:
                print(f"ok  empty plan id rejected: {str(exc).splitlines()[0]}")
            else:
                print("FAIL empty plan id inserted a row")
                conn.rollback()
                return 1
        conn.rollback()
    return 0


if __name__ == "__main__":
    sys.exit(main())
