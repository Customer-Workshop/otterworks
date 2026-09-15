#!/usr/bin/env python3
"""Read-only: digest the usage_events rows the Lakebase target holds.

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
        cur.execute("SELECT id, tenant_id, occurred_at, units, kind_cd "
                    "FROM billing.usage_events ORDER BY id")
        rows = cur.fetchall()
    body = "\n".join(repr(r) for r in rows)
    print(f"rows={len(rows)} sha256={hashlib.sha256(body.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
