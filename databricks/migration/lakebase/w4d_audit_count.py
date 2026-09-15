"""Count the billing_audit_log rows pkg_rating's converted code wrote on the wave branch.

Read-only: the recon ops call billing.fn_usage_rating, which calls log_msg (D-009), so the
evidence has to state how many audit rows the run left behind rather than imply none.
"""
from __future__ import annotations

import os

import psycopg


def main() -> None:
    with psycopg.connect(os.environ["OW_TP_LAKEBASE_DSN"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM billing.billing_audit_log WHERE module = 'RATING'")
            print("RATING audit rows:", cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM billing.billing_audit_log")
            print("total audit rows:", cur.fetchone()[0])


if __name__ == "__main__":
    main()
