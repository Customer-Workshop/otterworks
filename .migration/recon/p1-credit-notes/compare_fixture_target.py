#!/usr/bin/env python3
"""Read-only: print the credit_notes rows the Lakebase target holds, as a digest.

Used to check the target's state before and after a reload so the reload can be shown to
change nothing. Reads the target only; never writes, and never touches Oracle.
"""
from __future__ import annotations

import hashlib
import os
import sys

import psycopg


def main() -> int:
    dsn = os.environ["OW_TP_LAKEBASE_DSN"]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, tenant_id, issued_on, amount, remaining_amount "
                    "FROM billing.credit_notes ORDER BY id")
        rows = cur.fetchall()
    body = "\n".join(repr(r) for r in rows)
    print(f"rows={len(rows)} sha256={hashlib.sha256(body.encode()).hexdigest()}")
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
